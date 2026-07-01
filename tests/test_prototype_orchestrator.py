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

    async def test_reveal_returns_hidden_links_and_active_agents(self) -> None:
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
        result = await _orchestrator(store=store).analyze(
            PrototypeAnalyzeRequest(product="Vintage T9 hair trimmer")
        )

        reveal = store.get_reveal(result.run_id)

        self.assertGreaterEqual(len(reveal.china_sourcing_links), 1)
        self.assertIn("/t9", reveal.china_sourcing_links[0].url)
        self.assertEqual(reveal.sourcing_agents[0].name, "Amina")

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
        store=store or PrototypeStore(_temp_db()),
        cost_config=CostConfig(),
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


def _source(title: str, url: str, snippet: str, group: str) -> ProviderRawSource:
    return ProviderRawSource(
        title=title,
        url=url,
        snippet=snippet,
        region_hint=group,
        source_type="search_result",
    )


def _temp_db() -> Path:
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    handle.close()
    return Path(handle.name)
