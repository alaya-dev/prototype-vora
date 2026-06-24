import unittest

from app.agents.china_supplier_research import (
    ChinaSupplierExtraction,
    ChinaSupplierExtractionOption,
    ChinaSupplierResearchAgent,
)
from app.agents.market_research import (
    MarketResearchAgent,
    MarketResearchExtraction,
    TunisiaSupplierExtractionOption,
)
from app.services.tavily_client import TavilySearchResponse, TavilySearchResult


class RecordingTavilyClient:
    def __init__(self, result: TavilySearchResult) -> None:
        self.result = result
        self.queries: list[str] = []

    async def search(
        self,
        query: str,
        max_results: int,
    ) -> TavilySearchResponse:
        self.queries.append(query)
        return TavilySearchResponse(results=[self.result], warnings=[])


class RecordingGeminiClient:
    def __init__(self, response) -> None:
        self.response = response
        self.prompt = ""

    async def generate_json(self, prompt: str, response_model):
        self.prompt = prompt
        return self.response


class ResearchAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_tunisia_category_and_price_are_preserved(self) -> None:
        source_url = "https://tunisia.example/earbuds"
        tavily = RecordingTavilyClient(
            TavilySearchResult(
                title="Earbuds Tunisia",
                url=source_url,
                content="Wireless earbuds listed at 89 TND.",
            )
        )
        gemini = RecordingGeminiClient(
            MarketResearchExtraction(
                market_summary="A sourced Tunisia listing was found.",
                tunisia_suppliers=[
                    TunisiaSupplierExtractionOption(
                        name="Tunisia Store",
                        type="seller",
                        product_title="Wireless earbuds",
                        price_range_tnd="89 TND",
                        source_url=source_url,
                        confidence="high",
                        notes="Price appears in the search evidence.",
                    )
                ],
            )
        )
        agent = MarketResearchAgent(gemini, tavily, 2, 8)

        research = await agent.research(
            "wireless earbuds",
            "Consumer Electronics",
        )

        self.assertTrue(
            all("Consumer Electronics" in query for query in tavily.queries)
        )
        self.assertIn("Category: Consumer Electronics", gemini.prompt)
        self.assertEqual(research.tunisia_suppliers[0].price_range_tnd, "89 TND")
        self.assertIsNone(research.tunisia_suppliers[0].price_range_usd)

    async def test_china_category_price_and_moq_are_preserved(self) -> None:
        source_url = "https://china.example/earbuds"
        tavily = RecordingTavilyClient(
            TavilySearchResult(
                title="Earbuds Manufacturer",
                url=source_url,
                content="Price US$4-6 with MOQ 100 pieces.",
            )
        )
        gemini = RecordingGeminiClient(
            ChinaSupplierExtraction(
                china_suppliers=[
                    ChinaSupplierExtractionOption(
                        name="China Manufacturer",
                        type="manufacturer",
                        product_title="Wireless earbuds",
                        price_range_usd="US$4-6",
                        moq="100 pieces",
                        source_url=source_url,
                        confidence="high",
                        notes="Price and MOQ appear in the search evidence.",
                    )
                ]
            )
        )
        agent = ChinaSupplierResearchAgent(gemini, tavily, 2, 8)

        research = await agent.research(
            "wireless earbuds",
            "Consumer Electronics",
        )

        self.assertTrue(
            all("Consumer Electronics" in query for query in tavily.queries)
        )
        self.assertIn("Category: Consumer Electronics", gemini.prompt)
        self.assertEqual(research.china_suppliers[0].price_range_usd, "US$4-6")
        self.assertEqual(research.china_suppliers[0].moq, "100 pieces")
        self.assertIsNone(research.china_suppliers[0].price_range_tnd)
