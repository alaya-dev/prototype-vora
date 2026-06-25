import unittest

from app.agents.china_supplier_research import (
    ChinaSupplierExtraction,
    ChinaSupplierExtractionOption,
    GeminiChinaSupplierResearchAgent,
)
from app.agents.market_research import (
    GeminiTunisiaResearchAgent,
    TunisiaResearchExtraction,
    TunisiaSupplierExtractionOption,
)
from app.services.gemini_search_client import (
    GroundedResponse,
    GroundingCitation,
)


class RecordingGeminiSearchClient:
    def __init__(self, payload, citations: list[GroundingCitation]) -> None:
        self.grounded_response = GroundedResponse(
            payload=payload,
            citations=citations,
        )
        self.prompt = ""
        self.response_model = None

    async def generate_grounded_json(self, prompt: str, response_model):
        self.prompt = prompt
        self.response_model = response_model
        return self.grounded_response


class ResearchAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_tunisia_research_preserves_cited_price_and_category(self) -> None:
        source_url = "https://tunisia.example/earbuds"
        search_client = RecordingGeminiSearchClient(
            TunisiaResearchExtraction(
                market_summary="A sourced Tunisia listing was found.",
                tunisia_suppliers=[
                    TunisiaSupplierExtractionOption(
                        name="Tunisia Store",
                        type="seller",
                        product_title="Wireless earbuds",
                        price_range_tnd="89 TND",
                        source_url=source_url,
                        confidence="high",
                        notes="Price appears in the grounded source.",
                    )
                ],
            ),
            [GroundingCitation(title="Earbuds Tunisia", url=source_url)],
        )
        agent = GeminiTunisiaResearchAgent(search_client)

        research = await agent.research(
            "wireless earbuds",
            "Consumer Electronics",
        )

        self.assertIn("Category: Consumer Electronics", search_client.prompt)
        self.assertIn("untrusted", search_client.prompt.lower())
        self.assertIn("Google Search", search_client.prompt)
        self.assertEqual(research.tunisia_suppliers[0].price_range_tnd, "89 TND")
        self.assertIsNone(research.tunisia_suppliers[0].price_range_usd)
        self.assertIsNone(research.tunisia_suppliers[0].moq)
        self.assertEqual(research.tunisia_suppliers[0].confidence, "high")
        self.assertEqual(research.research_sources[0].url, source_url)
        self.assertEqual(
            research.research_sources[0].source_type,
            "tunisia_market",
        )

    async def test_tunisia_uncited_option_is_low_confidence_with_warning(self) -> None:
        search_client = RecordingGeminiSearchClient(
            TunisiaResearchExtraction(
                market_summary="A possible local seller was mentioned.",
                tunisia_suppliers=[
                    TunisiaSupplierExtractionOption(
                        name="Possible Seller",
                        type="seller",
                        product_title="Portable blender",
                        price_range_tnd=None,
                        source_url="https://uncited.example/blender",
                        confidence="high",
                        notes="The URL was not present in grounding annotations.",
                    )
                ],
            ),
            [],
        )

        research = await GeminiTunisiaResearchAgent(search_client).research(
            "portable blender"
        )

        self.assertIsNone(research.tunisia_suppliers[0].source_url)
        self.assertEqual(research.tunisia_suppliers[0].confidence, "low")
        self.assertTrue(
            any("citation" in warning.lower() for warning in research.warnings)
        )

    async def test_china_research_preserves_cited_price_moq_and_category(self) -> None:
        source_url = "https://china.example/earbuds"
        search_client = RecordingGeminiSearchClient(
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
                        notes="Price and MOQ appear in the grounded source.",
                    )
                ]
            ),
            [GroundingCitation(title="Earbuds Manufacturer", url=source_url)],
        )
        agent = GeminiChinaSupplierResearchAgent(search_client)

        research = await agent.research(
            "wireless earbuds",
            "Consumer Electronics",
        )

        self.assertIn("Category: Consumer Electronics", search_client.prompt)
        self.assertIn("untrusted", search_client.prompt.lower())
        self.assertIn("Google Search", search_client.prompt)
        self.assertEqual(research.china_suppliers[0].price_range_usd, "US$4-6")
        self.assertEqual(research.china_suppliers[0].moq, "100 pieces")
        self.assertIsNone(research.china_suppliers[0].price_range_tnd)
        self.assertEqual(research.china_suppliers[0].confidence, "high")
        self.assertEqual(
            research.research_sources[0].source_type,
            "china_supplier",
        )

    async def test_agents_cap_options_at_three(self) -> None:
        citations = [
            GroundingCitation(
                title=f"Source {index}",
                url=f"https://china.example/{index}",
            )
            for index in range(4)
        ]
        search_client = RecordingGeminiSearchClient(
            ChinaSupplierExtraction(
                china_suppliers=[
                    ChinaSupplierExtractionOption(
                        name=f"Supplier {index}",
                        type="manufacturer",
                        product_title="LED strip lights",
                        source_url=f"https://china.example/{index}",
                        confidence="medium",
                        notes="Grounded option.",
                    )
                    for index in range(4)
                ]
            ),
            citations,
        )

        research = await GeminiChinaSupplierResearchAgent(search_client).research(
            "LED strip lights"
        )

        self.assertEqual(len(research.china_suppliers), 3)
