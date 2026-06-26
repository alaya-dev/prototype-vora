import unittest

import httpx

from app.benchmark.providers.brave import BraveSearchAdapter
from app.benchmark.providers.exa import ExaAdapter
from app.benchmark.providers.perplexity import PerplexitySonarAdapter
from app.benchmark.providers.searxng import SearXNGAdapter
from app.benchmark.providers.serper import SerperAdapter
from app.benchmark.schemas import ProviderAnalysisResult
from app.config import Settings


class FakeResponse:
    def __init__(self, payload, status_code=200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("failed", request=None, response=None)

    def json(self):
        return self.payload


class FakeHttpClient:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)


class ProviderAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_serper_normalizes_organic_results(self) -> None:
        adapter = SerperAdapter(
            _settings(serper_api_key="serper", gemini_analysis_api_key="analysis")
        )
        adapter._client_factory = lambda: FakeHttpClient(
            [
                FakeResponse(
                    {
                        "organic": [
                            {
                                "title": "TN",
                                "link": "https://tn.example/item",
                                "snippet": "89 TND",
                            }
                        ]
                    }
                ),
                FakeResponse(
                    {
                        "organic": [
                            {
                                "title": "CN",
                                "link": "https://cn.example/item",
                                "snippet": "US$4 MOQ 100",
                            }
                        ]
                    }
                ),
            ]
        )
        adapter.settings = adapter.settings.__class__(
            **{**adapter.settings.__dict__, "search_queries_per_region": 1}
        )

        evidence = await adapter.search("wireless earbuds")

        self.assertEqual(evidence.provider_api_calls, 2)
        self.assertEqual(evidence.raw_queries_count, 2)
        self.assertEqual(len(evidence.sources), 2)
        self.assertEqual(evidence.sources[0].region_hint, "tunisia")

    async def test_brave_normalizes_web_results(self) -> None:
        adapter = BraveSearchAdapter(
            _settings(
                brave_search_api_key="brave",
                gemini_analysis_api_key="analysis",
            )
        )
        adapter._client_factory = lambda: FakeHttpClient(
            [
                FakeResponse(
                    {
                        "web": {
                            "results": [
                                {
                                    "title": "TN",
                                    "url": "https://tn.example/item",
                                    "description": "89 TND",
                                }
                            ]
                        }
                    }
                ),
                FakeResponse(
                    {
                        "web": {
                            "results": [
                                {
                                    "title": "CN",
                                    "url": "https://cn.example/item",
                                    "description": "US$4",
                                }
                            ]
                        }
                    }
                ),
            ]
        )
        adapter.settings = adapter.settings.__class__(
            **{**adapter.settings.__dict__, "search_queries_per_region": 1}
        )

        evidence = await adapter.search("wireless earbuds")

        self.assertEqual(evidence.provider_api_calls, 2)
        self.assertEqual(evidence.sources[1].region_hint, "china")

    async def test_exa_normalizes_content_results(self) -> None:
        adapter = ExaAdapter(
            _settings(exa_api_key="exa", gemini_analysis_api_key="analysis")
        )
        adapter._client_factory = lambda: FakeHttpClient(
            [
                FakeResponse(
                    {
                        "results": [
                            {
                                "title": "Result",
                                "url": "https://exa.example/item",
                                "text": "US$5",
                            }
                        ]
                    }
                ),
                FakeResponse({"results": []}),
            ]
        )
        adapter.settings = adapter.settings.__class__(
            **{**adapter.settings.__dict__, "search_queries_per_region": 1}
        )

        evidence = await adapter.search("portable blender")

        self.assertEqual(evidence.sources[0].content, "US$5")

    async def test_searxng_uses_json_search_endpoint(self) -> None:
        adapter = SearXNGAdapter(
            _settings(
                searxng_base_url="https://searx.example",
                gemini_analysis_api_key="analysis",
            )
        )
        adapter._client_factory = lambda: FakeHttpClient(
            [
                FakeResponse(
                    {
                        "results": [
                            {
                                "title": "Listing",
                                "url": "https://listing.example/item",
                                "content": "120 TND",
                            }
                        ]
                    }
                ),
                FakeResponse({"results": []}),
            ]
        )
        adapter.settings = adapter.settings.__class__(
            **{**adapter.settings.__dict__, "search_queries_per_region": 1}
        )

        evidence = await adapter.search("lamp")

        self.assertEqual(evidence.sources[0].snippet, "120 TND")

    async def test_perplexity_returns_analysis_without_gemini(self) -> None:
        adapter = PerplexitySonarAdapter(_settings(perplexity_api_key="pplx"))
        adapter._client_factory = lambda: FakeHttpClient(
            [
                FakeResponse(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": '{"market_summary":"Found","tunisia_cheapest_suppliers":[],"china_cheapest_suppliers":[],"research_sources":[],"warnings":[],"data_quality_notes":"","missing_data":{"tunisia":"","china":""}}'
                                }
                            }
                        ]
                    }
                )
            ]
        )

        result = await adapter.analyze_direct("lamp")

        self.assertIsInstance(result, ProviderAnalysisResult)
        self.assertEqual(result.market_summary, "Found")


def _settings(**overrides) -> Settings:
    values = dict(
        gemini_intent_api_key="intent-key",
        gemini_intent_model="gemini-3.1-flash-lite",
        gemini_analysis_api_key="analysis-key",
        gemini_analysis_model="gemini-3.1-flash-lite",
        gemini_api_key="",
        gemini_model="gemini-3.1-flash-lite",
        analysis_timeout_seconds=45,
        serper_api_key="",
        brave_search_api_key="",
        exa_api_key="",
        firecrawl_api_key="",
        perplexity_api_key="",
        searxng_base_url="",
        scavio_api_key="",
        scavio_base_url="",
        dataforseo_login="",
        dataforseo_password="",
        benchmark_provider_timeout_seconds=45,
        benchmark_max_providers_parallel=8,
        search_results_per_query=10,
        search_queries_per_region=4,
        max_raw_sources_per_provider=20,
    )
    values.update(overrides)
    return Settings(**values)
