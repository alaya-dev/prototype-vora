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
from app.prototype.schemas import (
    CostConfig,
    ExampleRetailPrice,
    LocalizedClientAnalysis,
    PrototypeAnalysisDraft,
    PrototypeAnalyzeRequest,
    RetailMarketSummary,
)
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


class SequentialImageProvider(FakeProvider):
    def __init__(self, provider_id: str) -> None:
        super().__init__(
            provider_id,
            {
                "china_sourcing": [_source("CN", "https://cn.example/t9", "US$2 factory price MOQ 100", "china_sourcing")],
                "tunisia_sourcing": [],
                "tunisia_retail": [
                    _source("Retail 1", "https://shop1.tn/t9", "35 TND boutique", "tunisia_retail"),
                    _source("Retail 2", "https://shop2.tn/t9", "42 TND boutique", "tunisia_retail"),
                ],
            },
        )

    async def search_group(self, product, group: str) -> ProviderEvidence:
        self.calls.append(group)
        if group == "tunisia_retail" and self.calls.count("tunisia_retail") > 1:
            return ProviderEvidence(
                provider_id=self.provider_id,
                sources=[
                    _source(
                        "T9 product image result",
                        "https://image.example/t9",
                        "T9 vintage hair trimmer image",
                        "tunisia_retail",
                        image_urls=["https://cdn.example/dedicated-image.jpg"],
                    )
                ],
                raw_queries_count=1,
                provider_api_calls=1,
            )
        return await super().search_group(product, group)


class PrototypeOrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_analysis_keeps_bilingual_gemini_narrative(self) -> None:
        draft = PrototypeAnalysisDraft(
            product_description="English fallback description.",
            localized_analysis=LocalizedClientAnalysis(
                product_description_en="English product description.",
                product_description_fr="Description produit en français.",
                price_analysis_en="English price analysis.",
                price_analysis_fr="Analyse prix en français.",
                market_analysis_en="English market analysis.",
                market_analysis_fr="Analyse marché en français.",
                business_reading_en="English business reading.",
                business_reading_fr="Lecture business en français.",
            ),
            china_sourcing_offers=[
                ChinaSourcingOffer(
                    name="CN Factory",
                    product_title="T9 vintage hair trimmer",
                    price_range_usd="US$2",
                    price_min_usd_numeric=2,
                    moq="100 pcs",
                    source_url="https://cn.example/t9",
                    confidence="high",
                    product_match="exact",
                )
            ],
            tunisia_retail_market=TunisiaRetailMarket(
                retail_offers=[
                    TunisiaRetailOffer(
                        seller_name="Shop 1",
                        seller_type="local_shop",
                        price_range_tnd="35 TND",
                        price_min_tnd_numeric=35,
                        source_url="https://shop1.tn/t9",
                        confidence="high",
                        product_match="exact",
                    ),
                    TunisiaRetailOffer(
                        seller_name="Shop 2",
                        seller_type="local_shop",
                        price_range_tnd="42 TND",
                        price_min_tnd_numeric=42,
                        source_url="https://shop2.tn/t9",
                        confidence="high",
                        product_match="exact",
                    ),
                ]
            ),
        )
        firecrawl = FakeProvider(
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

        result = await PrototypeResearchOrchestrator(
            FakeIntentClient(),
            FakeAnalysisClient(draft),
            [firecrawl],
            PrototypeStore(_temp_db()),
            CostConfig(),
        ).analyze(PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer"))

        self.assertEqual(result.localized_analysis.product_description_en, "English product description.")
        self.assertEqual(result.localized_analysis.product_description_fr, "Description produit en français.")
        self.assertEqual(result.localized_analysis.price_analysis_fr, "Analyse prix en français.")

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
                    _source("Retail 1", "https://shop1.tn/t9", "35 TND boutique", "tunisia_retail", image_urls=["https://cdn.example/t9.jpg"]),
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

        self.assertTrue((result.product_image_url or "").startswith("https://"))
        self.assertIsNotNone(result.product_image_source_url)
        self.assertEqual(result.product_image_confidence, "fallback")
        self.assertIn("source-domain visual", result.product_image_notes)

    async def test_markdown_image_is_used_when_provider_content_contains_product_image(self) -> None:
        firecrawl = FakeProvider(
            "firecrawl",
            {
                "china_sourcing": [
                    _source(
                        "T9 listing",
                        "https://cn.example/t9",
                        "US$2 factory price MOQ 100",
                        "china_sourcing",
                        content="![Product](https://cdn.example/from-markdown.jpg)",
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

        self.assertEqual(result.product_image_url, "https://cdn.example/from-markdown.jpg")
        self.assertEqual(result.product_image_source_url, "https://cn.example/t9")

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

        self.assertEqual(result.analysis_quantity_units, 1000)
        self.assertEqual(profit.source_unit_price_tnd, 6.2)
        self.assertEqual(profit.estimated_shipping_per_unit_tnd, 4)
        self.assertEqual(profit.estimated_customs_per_unit_tnd, 0.62)
        self.assertEqual(profit.estimated_misc_per_unit_tnd, 3)
        self.assertEqual(profit.estimated_landed_cost_per_unit_tnd, 13.82)
        self.assertIn("6.2 TND", profit.landed_cost_breakdown_notes)
        self.assertEqual(profit.estimated_meta_campaign_budget_tnd, 500)
        self.assertEqual(profit.digital_ad_budget_min_tnd, 300)
        self.assertEqual(profit.digital_ad_budget_max_tnd, 500)
        self.assertEqual(profit.digital_ad_budget_default_tnd, 500)
        self.assertEqual(profit.expected_units_sold_from_campaign, 100)
        self.assertEqual(profit.estimated_ad_cost_per_sold_unit_tnd, 5)
        self.assertIn("Digital advertising allocation: 500 TND total / 100", profit.ad_cost_notes)
        self.assertEqual(profit.estimated_margin_per_unit_tnd, 24.68)
        self.assertIsNone(profit.estimated_profit_for_100_units_tnd)
        self.assertEqual(profit.estimated_profit_for_1000_units_tnd, 24180)
        self.assertEqual(profit.net_profit_for_1000_after_advertising_min_tnd, 24180)
        self.assertEqual(profit.net_profit_for_1000_after_advertising_max_tnd, 24380)

    async def test_default_digital_advertising_budget_uses_300_to_500_range_and_400_default(self) -> None:
        result = await _orchestrator().analyze(
            PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer")
        )

        profit = result.profitability_estimate

        self.assertEqual(profit.digital_ad_budget_min_tnd, 300)
        self.assertEqual(profit.digital_ad_budget_max_tnd, 500)
        self.assertEqual(profit.digital_ad_budget_default_tnd, 400)
        self.assertEqual(profit.estimated_meta_campaign_budget_tnd, 400)
        self.assertEqual(profit.gross_profit_for_1000_before_marketing_tnd, 25680)
        self.assertEqual(profit.net_profit_for_1000_after_marketing_tnd, 25280)
        self.assertEqual(profit.net_profit_for_1000_after_advertising_min_tnd, 25180)
        self.assertEqual(profit.net_profit_for_1000_after_advertising_max_tnd, 25380)

    async def test_legacy_low_digital_ad_budget_values_fall_back_to_total_budget_defaults(self) -> None:
        result = await _orchestrator(
            cost_config=CostConfig(
                default_meta_campaign_budget_tnd=3,
                default_digital_ad_budget_min_tnd=3,
                default_digital_ad_budget_max_tnd=5,
            )
        ).analyze(PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer"))

        profit = result.profitability_estimate

        self.assertEqual(profit.digital_ad_budget_min_tnd, 300)
        self.assertEqual(profit.digital_ad_budget_max_tnd, 500)
        self.assertEqual(profit.digital_ad_budget_default_tnd, 400)
        self.assertEqual(profit.net_profit_for_1000_after_marketing_tnd, 25280)

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
        self.assertLessEqual(result.decision_scores.go_percent, 35)
        self.assertEqual(result.decision_scores.go_percent + result.decision_scores.no_go_percent, 100)
        self.assertTrue(result.decision_scores.go_reason)
        self.assertTrue(result.decision_scores.no_go_reason)
        self.assertTrue(result.decision_scores.score_explanation)
        self.assertTrue(result.decision_scores.why_go_score)
        self.assertTrue(result.decision_scores.why_no_go_score)
        self.assertIn("exact-match supplier option", " ".join(result.decision_scores.what_would_change_the_decision).lower())
        self.assertTrue(result.decision_summary)
        self.assertTrue(result.positive_signals)
        self.assertTrue(result.risk_signals)
        self.assertTrue(result.main_decision_factors)

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
        self.assertLessEqual(result.decision_scores.go_percent, 25)
        self.assertEqual(result.recommendation, "investigate_more")
        self.assertIn("margin buffer", result.decision_scores.score_explanation.lower())

    async def test_negative_margin_lowers_go_score(self) -> None:
        analysis = _analysis()
        analysis.tunisia_retail_market.retail_offers = [
            offer.model_copy(update={"price_min_tnd_numeric": 5, "price_range_tnd": "5 TND"})
            for offer in analysis.tunisia_retail_market.retail_offers
        ]

        result = await _orchestrator(analysis=analysis).analyze(
            PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer")
        )

        self.assertEqual(result.recommendation, "no_go")
        self.assertLessEqual(result.decision_scores.go_percent, 15)
        self.assertEqual(result.decision_scores.go_percent + result.decision_scores.no_go_percent, 100)
        self.assertEqual(result.decision_scores.dominant_side, "no_go")
        self.assertTrue(any("not attractive enough" in reason.lower() for reason in result.decision_scores.why_no_go_score))
        self.assertTrue(result.decision_scores.main_decision_factors)

    async def test_seller_density_is_low_for_one_or_two_unique_retail_sellers(self) -> None:
        result = await _orchestrator(analysis=_analysis_with_retail_sellers(2)).analyze(
            PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer")
        )

        self.assertEqual(result.retail_market_summary.seller_density, "low")

    async def test_seller_density_is_medium_for_three_to_five_unique_retail_sellers(self) -> None:
        result = await _orchestrator(analysis=_analysis_with_retail_sellers(4)).analyze(
            PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer")
        )

        self.assertEqual(result.retail_market_summary.seller_density, "medium")

    async def test_seller_density_is_high_for_six_or_more_unique_retail_sellers(self) -> None:
        result = await _orchestrator(analysis=_analysis_with_retail_sellers(6)).analyze(
            PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer")
        )

        self.assertEqual(result.retail_market_summary.seller_density, "high")

    async def test_seller_density_uses_domains_when_seller_names_are_missing(self) -> None:
        analysis = _analysis_with_retail_sellers(3)
        analysis.tunisia_retail_market.retail_offers = [
            offer.model_copy(update={"seller_name": ""})
            for offer in analysis.tunisia_retail_market.retail_offers
        ]

        result = await _orchestrator(analysis=analysis).analyze(
            PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer")
        )

        self.assertEqual(result.retail_market_summary.seller_density, "medium")

    async def test_firecrawl_sufficient_skips_tavily_and_exa(self) -> None:
        firecrawl = FakeProvider(
            "firecrawl",
            {
                "china_sourcing": [_source("CN", "https://cn.example/t9", "US$2 factory price MOQ 100", "china_sourcing")],
                "tunisia_sourcing": [_source("TN gros", "https://grossiste.tn/t9", "prix gros 8 TND", "tunisia_sourcing")],
                "tunisia_retail": [
                    _source("Retail 1", "https://shop1.tn/t9", "35 TND boutique", "tunisia_retail", image_urls=["https://cdn.example/t9.jpg"]),
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
        self.assertEqual(result.hidden_sourcing_links.tunisia_sourcing_links, [])

    async def test_reveal_returns_cheapest_china_product_links_without_seller_contacts(self) -> None:
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
        analysis = _analysis()
        analysis.china_sourcing_offers = [
            analysis.china_sourcing_offers[0].model_copy(
                update={
                    "name": "Higher Factory",
                    "product_title": "T9 higher price",
                    "price_range_usd": "US$3",
                    "price_min_usd_numeric": 3,
                    "price_max_usd_numeric": 3,
                    "source_url": "https://cn.example/t9-higher",
                }
            ),
            analysis.china_sourcing_offers[0].model_copy(
                update={
                    "name": "Cheapest Factory",
                    "product_title": "T9 cheapest offer",
                    "price_range_usd": "US$1.20",
                    "price_min_usd_numeric": 1.2,
                    "price_max_usd_numeric": 1.2,
                    "source_url": "https://cn.example/t9-cheapest",
                }
            ),
        ]
        result = await _orchestrator(store=store, analysis=analysis).analyze(
            PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer")
        )

        reveal = await _orchestrator(store=store).reveal(result.run_id)

        self.assertGreaterEqual(len(reveal.china_sourcing_links), 2)
        self.assertEqual(reveal.china_sourcing_links[0].url, "https://cn.example/t9-cheapest")
        self.assertEqual(reveal.china_sourcing_links[0].title, "T9 cheapest offer")
        self.assertIn("3.72 TND", reveal.china_sourcing_links[0].price or "")
        self.assertEqual(reveal.seller_contacts, [])
        self.assertEqual(reveal.sourcing_agents[0].name, "Amina")
        detail = store.get_run_detail(result.run_id)
        self.assertIn("china_sourcing_links", detail.hidden_links)
        self.assertFalse(detail.contact_enrichment_called)
        self.assertEqual(detail.contacts_found_count, 0)

    async def test_reveal_keeps_tunisia_links_and_sourcing_agents(self) -> None:
        store = PrototypeStore(_temp_db())
        store.upsert_sourcing_agent({"name": "Amina", "email": "amina@example.com", "active": True})
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
        analysis = _analysis()
        result = await _orchestrator(
            firecrawl=firecrawl,
            store=store,
            analysis=analysis,
        ).analyze(PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer"))

        reveal = await _orchestrator(store=store).reveal(result.run_id)

        self.assertEqual(reveal.china_sourcing_links[0].url, "https://cn.example/t9")
        self.assertEqual(reveal.tunisia_sourcing_links[0].url, "https://grossiste.tn/t9")
        self.assertEqual([agent.name for agent in reveal.sourcing_agents], ["Amina"])
        detail = store.get_run_detail(result.run_id)
        self.assertEqual(detail.contact_provider_attempts, 0)
        self.assertEqual(detail.contact_search_api_calls, 0)
        self.assertEqual(detail.contacts_found_count, 0)

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

        self.assertEqual(reveal.china_sourcing_links[0].url, "https://cn.example/t9")
        self.assertEqual(reveal.seller_contacts, [])
        self.assertEqual([agent.name for agent in reveal.sourcing_agents], ["Amina"])
        detail = store.get_run_detail(result.run_id)
        self.assertEqual(detail.contacts_found_count, 0)
        self.assertEqual(detail.contact_cards_rejected_count, 0)

    async def test_dedicated_image_fallback_runs_when_initial_evidence_has_no_image(self) -> None:
        firecrawl = SequentialImageProvider("firecrawl")

        result = await _orchestrator(firecrawl=firecrawl).analyze(
            PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer")
        )

        self.assertEqual(result.product_image_url, "https://cdn.example/dedicated-image.jpg")
        self.assertEqual(result.product_image_source_url, "https://image.example/t9")
        self.assertGreaterEqual(firecrawl.calls.count("tunisia_retail"), 2)

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

    async def test_retail_summary_falls_back_to_example_prices_when_aggregate_fields_are_missing(self) -> None:
        draft = PrototypeAnalysisDraft(
            product_description="Fallback retail summary test.",
            retail_market_summary=RetailMarketSummary(
                retail_price_range_tnd="",
                retail_min_tnd=None,
                retail_max_tnd=None,
                retail_avg_tnd=None,
                example_retail_prices=[
                    ExampleRetailPrice(seller_name="Wamia", price_tnd=13.9, price_range_tnd="13.9 TND"),
                    ExampleRetailPrice(seller_name="Best Buy Tunisie", price_tnd=35, price_range_tnd="35 TND"),
                ],
            ),
        )
        result = await _orchestrator(analysis=draft).analyze(
            PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer")
        )

        self.assertEqual(result.retail_market_summary.retail_min_tnd, 13.9)
        self.assertEqual(result.retail_market_summary.retail_max_tnd, 35)
        self.assertEqual(result.retail_market_summary.retail_avg_tnd, 24.45)
        self.assertEqual(result.retail_market_summary.retail_price_range_tnd, "13.9 to 35 TND")


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


def _analysis_with_retail_sellers(count: int) -> ProviderAnalysisResult:
    analysis = _analysis()
    offers = []
    for index in range(count):
        price = 35 + index
        offers.append(
            TunisiaRetailOffer(
                seller_name=f"Shop {index + 1}",
                seller_type="local_shop",
                price_range_tnd=f"{price} TND",
                price_min_tnd_numeric=price,
                source_url=f"https://shop{index + 1}.tn/t9",
                evidence_level="direct",
                price_evidence="direct",
                product_match="exact",
                confidence="high",
            )
        )
    analysis.tunisia_retail_market = analysis.tunisia_retail_market.model_copy(
        update={"retail_offers": offers}
    )
    return analysis


def _source(
    title: str,
    url: str,
    snippet: str,
    group: str,
    image_urls: list[str] | None = None,
    content: str | None = None,
) -> ProviderRawSource:
    return ProviderRawSource(
        title=title,
        url=url,
        snippet=snippet,
        content=content,
        region_hint=group,
        source_type="search_result",
        image_urls=image_urls or [],
    )


def _temp_db() -> Path:
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    handle.close()
    return Path(handle.name)
