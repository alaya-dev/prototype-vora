import tempfile
import unittest
from pathlib import Path

from app.benchmark.schemas import (
    ChinaSourcingOffer,
    ProviderAnalysisResult,
    ProviderEvidence,
    ProviderRawSource,
    TunisiaRetailMarket,
    TunisiaRetailOffer,
    TunisiaSourcingOffer,
)
from app.prototype.research_orchestrator import PrototypeResearchOrchestrator
from app.prototype.schemas import CostConfig, PrototypeAnalyzeRequest
from app.prototype.storage import PrototypeStore
from app.schemas import IntentResult, ProductUnderstanding


class FakeIntentClient:
    def __init__(self) -> None:
        self.calls = 0

    async def classify(self, product: str) -> IntentResult:
        self.calls += 1
        return IntentResult(
            is_valid_product=True,
            normalized_product="T9 vintage hair trimmer",
            reason="Valid product.",
            product_understanding=ProductUnderstanding(
                original_product=product,
                normalized_product="T9 vintage hair trimmer",
                product_category="hair trimmer",
                brand_or_model="T9",
                english_search_name="T9 vintage hair trimmer",
                french_search_name="tondeuse cheveux T9 vintage",
                must_include_terms=["T9"],
            ),
        )


class FakeAnalysisClient:
    def __init__(self, analysis: ProviderAnalysisResult) -> None:
        self.analysis = analysis
        self.calls = []

    async def extract_client_analysis(self, product, evidence, cost_config, quantity_scenarios):
        self.calls.append((product, evidence, cost_config, quantity_scenarios))
        return self.analysis


class FakeProvider:
    def __init__(self, provider_id: str, sources_by_group: dict[str, list[ProviderRawSource]]) -> None:
        self.provider_id = provider_id
        self.provider_name = provider_id.title()
        self.sources_by_group = sources_by_group
        self.calls: list[str] = []

    async def search_group(self, product, group: str) -> ProviderEvidence:
        self.calls.append(group)
        return ProviderEvidence(
            provider_id=self.provider_id,
            sources=self.sources_by_group.get(group, []),
            raw_queries_count=1,
            provider_api_calls=1,
        )


class PrototypeOrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_product_image_metadata_prefers_source_backed_images(self) -> None:
        firecrawl = FakeProvider(
            "firecrawl",
            {
                "china_sourcing": [
                    _source(
                        "T9 hair trimmer",
                        "https://cn.example/t9",
                        "US$2 factory price MOQ 100",
                        "china_sourcing",
                        image_urls=["https://cdn.example/t9.jpg"],
                    )
                ],
                "tunisia_sourcing": [],
                "tunisia_retail": [
                    _source("Retail 1", "https://shop1.tn/t9", "35 TND boutique", "tunisia_retail"),
                    _source("Retail 2", "https://shop2.tn/t9", "42 TND boutique", "tunisia_retail"),
                ],
            },
        )

        result = await _orchestrator(firecrawl=firecrawl).analyze(
            PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer")
        )

        self.assertEqual(result.product_image_url, "https://cdn.example/t9.jpg")
        self.assertEqual(result.product_image_source_url, "https://cn.example/t9")
        self.assertIn(result.product_image_confidence, {"high", "medium"})

    async def test_missing_product_image_returns_fallback_metadata(self) -> None:
        result = await _orchestrator().analyze(
            PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer")
        )

        self.assertIsNone(result.product_image_url)
        self.assertIsNone(result.product_image_source_url)
        self.assertEqual(result.product_image_confidence, "fallback")
        self.assertIn("No reliable source-backed product image was found", result.product_image_notes)

    async def test_source_unit_price_landed_cost_and_total_campaign_profit_are_separate(self) -> None:
        result = await _orchestrator(cost_config=CostConfig(
            usd_to_tnd_rate=3.1,
            default_shipping_per_unit_tnd=4,
            default_customs_or_import_rate_percent=10,
            default_misc_cost_per_unit_tnd=3,
            default_meta_campaign_budget_tnd=500,
            default_expected_units_sold_from_campaign=100,
        )).analyze(
            PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer")
        )

        profit = result.profitability_estimate

        self.assertEqual(profit.source_unit_price_tnd, 6.2)
        self.assertEqual(profit.estimated_shipping_per_unit_tnd, 4)
        self.assertEqual(profit.estimated_customs_per_unit_tnd, 0.62)
        self.assertEqual(profit.estimated_misc_per_unit_tnd, 3)
        self.assertEqual(profit.estimated_landed_cost_per_unit_tnd, 13.82)
        self.assertIn("6.2 TND", profit.landed_cost_breakdown_notes)
        self.assertEqual(profit.estimated_meta_campaign_budget_tnd, 500)
        self.assertEqual(profit.expected_units_sold_from_campaign, 100)
        self.assertEqual(profit.estimated_ad_cost_per_sold_unit_tnd, 5)
        self.assertIn("500 TND / 100", profit.ad_cost_notes)
        self.assertEqual(profit.estimated_margin_per_unit_tnd, 24.68)
        self.assertIsNone(profit.estimated_profit_for_100_units_tnd)
        self.assertEqual(profit.estimated_profit_for_1000_units_tnd, 24180)

    async def test_recommendation_is_conservative_for_equivalent_oem_or_weak_evidence(self) -> None:
        analysis = _analysis()
        analysis.china_sourcing_offers[0] = analysis.china_sourcing_offers[0].model_copy(
            update={
                "product_match": "broad",
                "match_notes": "Equivalent OEM fan heater, not exact branded product.",
            }
        )

        result = await _orchestrator(analysis=analysis).analyze(
            PrototypeAnalyzeRequest(product="COALA RS2000W-IR 1500W Fan Heater")
        )

        self.assertEqual(result.recommendation, "investigate_more")
        self.assertTrue(any("Equivalent OEM" in risk for risk in result.profitability_estimate.risks))

    async def test_zero_landed_assumptions_do_not_create_confident_landed_cost(self) -> None:
        result = await _orchestrator(
            cost_config=CostConfig(
                default_shipping_per_unit_tnd=0,
                default_customs_or_import_rate_percent=0,
                default_handling_per_unit_tnd=0,
                default_misc_cost_per_unit_tnd=0,
                default_meta_campaign_budget_tnd=300,
            )
        ).analyze(PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer"))

        profit = result.profitability_estimate

        self.assertEqual(profit.source_unit_price_tnd, 6.2)
        self.assertIsNone(profit.estimated_landed_cost_per_unit_tnd)
        self.assertIsNone(profit.estimated_profit_per_unit_tnd)
        self.assertIn("requires shipping/import/handling assumptions", profit.landed_cost_breakdown_notes)

    async def test_firecrawl_sufficient_skips_tavily_and_exa(self) -> None:
        firecrawl = FakeProvider(
            "firecrawl",
            {
                "china_sourcing": [_source("CN", "https://cn.example/t9", "US$2 factory price MOQ 100", "china_sourcing")],
                "tunisia_sourcing": [_source("TN gros", "https://grossiste.tn/t9", "prix gros 8 TND", "tunisia_sourcing")],
                "tunisia_retail": [
                    _source("Retail 1", "https://shop1.tn/t9", "35 TND boutique", "tunisia_retail"),
                    _source("Retail 2", "https://shop2.tn/t9", "42 TND boutique", "tunisia_retail"),
                ],
            },
        )
        tavily = FakeProvider("tavily", {})
        exa = FakeProvider("exa", {})

        result = await _orchestrator(
            firecrawl,
            tavily,
            exa,
            analysis=_analysis(include_tunisia_sourcing=False),
        ).analyze(
            PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer")
        )

        self.assertEqual(firecrawl.calls, ["china_sourcing", "tunisia_sourcing", "tunisia_retail"])
        self.assertEqual(tavily.calls, [])
        self.assertEqual(exa.calls, [])
        self.assertTrue(result.links_hidden)

    async def test_missing_groups_fall_back_tavily_then_exa_only_for_missing_group(self) -> None:
        firecrawl = FakeProvider(
            "firecrawl",
            {
                "china_sourcing": [_source("CN", "https://cn.example/t9", "US$2 factory price", "china_sourcing")],
            },
        )
        tavily = FakeProvider("tavily", {"tunisia_retail": [_source("Retail", "https://shop.tn/t9", "35 TND", "tunisia_retail")]})
        exa = FakeProvider(
            "exa",
            {
                "tunisia_retail": [_source("Retail 2", "https://shop2.tn/t9", "39 TND", "tunisia_retail")],
                "tunisia_sourcing": [],
            },
        )

        result = await _orchestrator(
            firecrawl,
            tavily,
            exa,
            analysis=_analysis(include_tunisia_sourcing=False),
        ).analyze(
            PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer")
        )

        self.assertIn("tunisia_sourcing", tavily.calls)
        self.assertIn("tunisia_sourcing", exa.calls)
        self.assertIn("tunisia_retail", tavily.calls)
        self.assertIn("tunisia_retail", exa.calls)
        self.assertFalse(result.sourcing_summary.tunisia_wholesale_found)
        self.assertIn("No reliable Tunisian wholesale sourcing offer", result.sourcing_summary.tunisia_wholesale_summary)
        self.assertTrue(any("No reliable Tunisian wholesale" in warning for warning in result.warnings))

    async def test_reveal_returns_seller_contacts_without_china_product_links(self) -> None:
        store = PrototypeStore(_temp_db())
        store.upsert_sourcing_agent(
            {
                "name": "Amina",
                "company_name": "VORA Sourcing",
                "country_or_region": "Tunisia/China",
                "email": "amina@example.com",
                "phone": "",
                "whatsapp": "+21600000000",
                "website": "https://vora.example",
                "notes": "Prototype contact",
                "active": True,
            }
        )
        contact_provider = FakeProvider(
            "firecrawl",
            {
                "china_sourcing": [
                    _source(
                        "CN Factory contact",
                        "https://contact.example/cn-factory",
                        "Email sales@cnfactory.com WhatsApp +8613800138000",
                        "china_sourcing",
                    )
                ]
            },
        )
        result = await _orchestrator(store=store, contact_providers=[contact_provider]).analyze(
            PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer")
        )
        self.assertEqual(contact_provider.calls, [])

        reveal = await _orchestrator(store=store, contact_providers=[contact_provider]).reveal(result.run_id)

        self.assertEqual(reveal.china_sourcing_links, [])
        self.assertEqual(reveal.seller_contacts[0].email, "sales@cnfactory.com")
        self.assertEqual(reveal.seller_contacts[0].whatsapp, "+8613800138000")
        self.assertEqual(reveal.sourcing_agents[0].name, "Amina")
        detail = store.get_run_detail(result.run_id)
        self.assertIn("china_sourcing_links", detail.hidden_links)
        self.assertTrue(detail.contact_enrichment_called)
        self.assertEqual(detail.contact_provider_attempts, 1)
        self.assertGreater(detail.contact_search_api_calls, 0)
        self.assertEqual(detail.contacts_found_count, 1)
        self.assertEqual(detail.contacts_with_email_count, 1)
        self.assertEqual(detail.contacts_with_whatsapp_count, 1)

    async def test_reveal_mines_saved_china_listing_evidence_before_contact_search(self) -> None:
        store = PrototypeStore(_temp_db())
        firecrawl = FakeProvider(
            "firecrawl",
            {
                "china_sourcing": [
                    _source(
                        "MarketUnion T9 listing",
                        "https://marketunion.example/t9",
                        "US$2 factory price MOQ 100. Contact sales@marketunion.example WhatsApp +8613800138000",
                        "china_sourcing",
                    )
                ],
                "tunisia_sourcing": [],
                "tunisia_retail": [
                    _source("Retail 1", "https://shop1.tn/t9", "35 TND boutique", "tunisia_retail"),
                    _source("Retail 2", "https://shop2.tn/t9", "42 TND boutique", "tunisia_retail"),
                ],
            },
        )
        contact_provider = FakeProvider("firecrawl", {})
        analysis = _analysis()
        analysis.china_sourcing_offers[0] = analysis.china_sourcing_offers[0].model_copy(
            update={
                "name": "MarketUnion",
                "product_title": "MarketUnion T9 listing",
                "source_url": "https://marketunion.example/t9",
            }
        )
        result = await _orchestrator(
            firecrawl=firecrawl,
            store=store,
            contact_providers=[contact_provider],
            analysis=analysis,
        ).analyze(PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer"))

        reveal = await _orchestrator(store=store, contact_providers=[contact_provider]).reveal(result.run_id)

        self.assertEqual(contact_provider.calls, [])
        self.assertEqual(reveal.china_sourcing_links, [])
        self.assertEqual(reveal.seller_contacts[0].email, "sales@marketunion.example")
        self.assertEqual(reveal.seller_contacts[0].whatsapp, "+8613800138000")
        detail = store.get_run_detail(result.run_id)
        self.assertEqual(detail.contact_provider_attempts, 0)
        self.assertEqual(detail.contact_search_api_calls, 0)
        self.assertEqual(detail.contacts_found_count, 1)

    async def test_reveal_hides_empty_contact_cards_and_keeps_agents(self) -> None:
        store = PrototypeStore(_temp_db())
        store.upsert_sourcing_agent({"name": "Amina", "email": "amina@example.com", "active": True})
        contact_provider = FakeProvider(
            "firecrawl",
            {
                "china_sourcing": [
                    _source(
                        "CN listing without contact",
                        "https://contact.example/no-contact",
                        "US$2 MOQ 100 SKU 2853726960697",
                        "china_sourcing",
                    )
                ]
            },
        )
        result = await _orchestrator(store=store, contact_providers=[contact_provider]).analyze(
            PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer")
        )

        reveal = await _orchestrator(store=store, contact_providers=[contact_provider]).reveal(result.run_id)

        self.assertEqual(reveal.seller_contacts, [])
        self.assertEqual([agent.name for agent in reveal.sourcing_agents], ["Amina"])
        detail = store.get_run_detail(result.run_id)
        self.assertEqual(detail.contacts_found_count, 0)
        self.assertGreaterEqual(detail.contact_cards_rejected_count, 1)

    async def test_client_retail_examples_keep_market_product_links(self) -> None:
        result = await _orchestrator().analyze(
            PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer")
        )

        retail_links = [
            item.source_url
            for item in result.retail_market_summary.example_retail_prices
        ]

        self.assertIn("https://shop1.tn/t9", retail_links)
        self.assertIn("https://shop2.tn/t9", retail_links)


def _orchestrator(
    firecrawl: FakeProvider | None = None,
    tavily: FakeProvider | None = None,
    exa: FakeProvider | None = None,
    store: PrototypeStore | None = None,
    analysis: ProviderAnalysisResult | None = None,
    contact_providers: list[FakeProvider] | None = None,
    cost_config: CostConfig | None = None,
) -> PrototypeResearchOrchestrator:
    firecrawl = firecrawl or FakeProvider(
        "firecrawl",
        {
            "china_sourcing": [_source("CN", "https://cn.example/t9", "US$2 factory price MOQ 100", "china_sourcing")],
            "tunisia_sourcing": [],
            "tunisia_retail": [
                _source("Retail 1", "https://shop1.tn/t9", "35 TND boutique", "tunisia_retail"),
                _source("Retail 2", "https://shop2.tn/t9", "42 TND boutique", "tunisia_retail"),
            ],
        },
    )
    analysis = analysis or _analysis()
    return PrototypeResearchOrchestrator(
        intent_client=FakeIntentClient(),
        analysis_client=FakeAnalysisClient(analysis),
        providers=[firecrawl, tavily or FakeProvider("tavily", {}), exa or FakeProvider("exa", {})],
        contact_providers=contact_providers,
        store=store or PrototypeStore(_temp_db()),
        cost_config=cost_config or CostConfig(),
    )


def _analysis(include_tunisia_sourcing: bool = True) -> ProviderAnalysisResult:
    tunisia_sourcing = [
        TunisiaSourcingOffer(
            name="TN Distributor",
            type="distributor",
            product_title="T9 tondeuse cheveux",
            price_range_tnd="8 TND",
            price_min_tnd_numeric=8,
            source_url="https://grossiste.tn/t9",
            evidence_level="direct",
            price_evidence="direct",
            product_match="exact",
            confidence="high",
            notes="prix gros fournisseur Tunisie",
        )
    ] if include_tunisia_sourcing else []
    return ProviderAnalysisResult(
        market_summary="T9 market.",
        china_sourcing_offers=[
            ChinaSourcingOffer(
                name="CN Factory",
                type="factory",
                product_title="T9 hair trimmer",
                price_range_usd="US$2-3",
                price_min_usd_numeric=2,
                price_max_usd_numeric=3,
                moq="100 pcs",
                moq_numeric=100,
                source_url="https://cn.example/t9",
                evidence_level="direct",
                price_evidence="direct",
                moq_evidence="direct",
                confidence="high",
                product_match="exact",
            )
        ],
        tunisia_sourcing_offers=tunisia_sourcing,
        tunisia_retail_market=TunisiaRetailMarket(
            retail_offers=[
                TunisiaRetailOffer(
                    seller_name="Shop 1",
                    seller_type="local_shop",
                    price_range_tnd="35 TND",
                    price_min_tnd_numeric=35,
                    source_url="https://shop1.tn/t9",
                    evidence_level="direct",
                    price_evidence="direct",
                    product_match="exact",
                    confidence="high",
                ),
                TunisiaRetailOffer(
                    seller_name="Shop 2",
                    seller_type="local_shop",
                    price_range_tnd="42 TND",
                    price_min_tnd_numeric=42,
                    source_url="https://shop2.tn/t9",
                    evidence_level="direct",
                    price_evidence="direct",
                    product_match="exact",
                    confidence="high",
                ),
            ]
        ),
    )


def _source(title: str, url: str, snippet: str, group: str, image_urls: list[str] | None = None) -> ProviderRawSource:
    return ProviderRawSource(
        title=title,
        url=url,
        snippet=snippet,
        region_hint=group,
        source_type="search_result",
        image_urls=image_urls or [],
    )


def _temp_db() -> Path:
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    handle.close()
    return Path(handle.name)
