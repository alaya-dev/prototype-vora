import unittest

import httpx

from app.benchmark.providers.brave import BraveSearchAdapter
from app.benchmark.providers.dataforseo import DataForSEOAdapter
from app.benchmark.providers.exa import ExaAdapter
from app.benchmark.providers.firecrawl import FirecrawlAdapter
from app.benchmark.providers.perplexity import PerplexitySonarAdapter
from app.benchmark.providers.scavio import ScavioAdapter
from app.benchmark.providers.searxng import SearXNGAdapter
from app.benchmark.providers.serper import SerperAdapter
from app.benchmark.providers.base import ProviderAdapterError, ProviderNotConfiguredError
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
                                "title": "TN sourcing",
                                "link": "https://tn-source.example/item",
                                "snippet": "prix gros 70 TND",
                            }
                        ]
                    }
                ),
                FakeResponse(
                    {
                        "organic": [
                            {
                                "title": "TN retail",
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

        self.assertEqual(evidence.provider_api_calls, 3)
        self.assertEqual(evidence.raw_queries_count, 3)
        self.assertEqual(len(evidence.sources), 3)
        self.assertEqual(evidence.sources[0].region_hint, "china_sourcing")
        self.assertEqual(evidence.sources[1].region_hint, "tunisia_sourcing")
        self.assertEqual(evidence.sources[2].region_hint, "tunisia_retail")

    async def test_serper_cap_preserves_china_sources_when_limits_are_tight(self) -> None:
        adapter = SerperAdapter(
            _settings(serper_api_key="serper", gemini_analysis_api_key="analysis")
        )
        adapter._client_factory = lambda: FakeHttpClient(
            [
                FakeResponse(
                    {
                        "organic": [
                            {
                                "title": "CN 1",
                                "link": "https://cn.example/1",
                                "snippet": "US$4 MOQ 100",
                            }
                        ]
                    }
                ),
                FakeResponse(
                    {
                        "organic": [
                            {
                                "title": "CN 2",
                                "link": "https://cn.example/2",
                                "snippet": "US$5 MOQ 50",
                            }
                        ]
                    }
                ),
                FakeResponse(
                    {
                        "organic": [
                            {
                                "title": "TN 1",
                                "link": "https://tn.example/1",
                                "snippet": "120 TND",
                            }
                        ]
                    }
                ),
                FakeResponse(
                    {
                        "organic": [
                            {
                                "title": "TN 2",
                                "link": "https://tn.example/2",
                                "snippet": "110 TND",
                            }
                        ]
                    }
                ),
            ]
        )
        adapter.settings = adapter.settings.__class__(
            **{
                **adapter.settings.__dict__,
                "search_queries_per_region": 2,
                "max_raw_sources_per_provider": 2,
            }
        )

        evidence = await adapter.search("wireless earbuds")

        self.assertEqual(len(evidence.sources), 2)
        self.assertEqual([source.region_hint for source in evidence.sources], ["china_sourcing", "tunisia_sourcing"])

    async def test_serper_cap_prefers_china_when_only_one_source_fits(self) -> None:
        adapter = SerperAdapter(
            _settings(serper_api_key="serper", gemini_analysis_api_key="analysis")
        )
        adapter._client_factory = lambda: FakeHttpClient(
            [
                FakeResponse(
                    {
                        "organic": [
                            {
                                "title": "TN 1",
                                "link": "https://tn.example/1",
                                "snippet": "120 TND",
                            }
                        ]
                    }
                ),
                FakeResponse(
                    {
                        "organic": [
                            {
                                "title": "CN 1",
                                "link": "https://cn.example/1",
                                "snippet": "US$4 MOQ 100",
                            }
                        ]
                    }
                ),
            ]
        )
        adapter.settings = adapter.settings.__class__(
            **{
                **adapter.settings.__dict__,
                "search_queries_per_region": 1,
                "max_raw_sources_per_provider": 1,
            }
        )

        evidence = await adapter.search("wireless earbuds")

        self.assertEqual(len(evidence.sources), 1)
        self.assertEqual(evidence.sources[0].region_hint, "china_sourcing")

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
                                    "title": "CN",
                                    "url": "https://cn.example/item",
                                    "description": "US$4",
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
                                    "title": "TN sourcing",
                                    "url": "https://tn-source.example/item",
                                    "description": "prix gros 70 TND",
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
                                    "title": "TN retail",
                                    "url": "https://tn.example/item",
                                    "description": "89 TND",
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

        self.assertEqual(evidence.provider_api_calls, 3)
        self.assertEqual(evidence.sources[0].region_hint, "china_sourcing")

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
                FakeResponse({"results": []}),
            ]
        )
        adapter.settings = adapter.settings.__class__(
            **{**adapter.settings.__dict__, "search_queries_per_region": 1}
        )

        evidence = await adapter.search("lamp")

        self.assertEqual(evidence.sources[0].snippet, "120 TND")

    async def test_firecrawl_search_normalizes_results_and_counts_usage(self) -> None:
        adapter = FirecrawlAdapter(
            _settings(
                firecrawl_api_key="firecrawl-key",
                gemini_analysis_api_key="analysis",
            )
        )
        adapter._client_factory = lambda: FakeHttpClient(
            [
                FakeResponse(
                    {
                        "success": True,
                        "data": {
                            "web": [
                                {
                                    "title": "CN listing",
                                    "url": "https://cn.example/item",
                                    "description": "US$4 MOQ 100",
                                }
                            ]
                        },
                    }
                ),
                FakeResponse(
                    {
                        "success": True,
                        "data": {
                            "web": [
                                {
                                    "title": "TN sourcing",
                                    "url": "https://tn-source.example/item",
                                    "description": "prix gros 70 TND",
                                    "markdown": "# TN sourcing\nprix gros 70 TND",
                                }
                            ]
                        },
                    }
                ),
                FakeResponse(
                    {
                        "success": True,
                        "data": {
                            "web": [
                                {
                                    "title": "TN retail",
                                    "url": "https://tn.example/item",
                                    "description": "89 TND",
                                    "markdown": "# TN listing\n89 TND",
                                }
                            ]
                        },
                    }
                ),
            ]
        )
        adapter.settings = adapter.settings.__class__(
            **{
                **adapter.settings.__dict__,
                "search_queries_per_region": 1,
                "search_results_per_query": 3,
            }
        )

        evidence = await adapter.search("wireless earbuds")

        self.assertEqual(evidence.provider_api_calls, 3)
        self.assertEqual(evidence.raw_queries_count, 3)
        self.assertEqual(len(evidence.sources), 3)
        self.assertEqual(evidence.sources[0].snippet, "US$4 MOQ 100")
        self.assertEqual(evidence.sources[0].region_hint, "china_sourcing")
        self.assertEqual(evidence.sources[1].region_hint, "tunisia_sourcing")
        self.assertEqual(evidence.sources[2].content, "# TN listing\n89 TND")

    async def test_firecrawl_accepts_documented_list_data_shape(self) -> None:
        adapter = FirecrawlAdapter(
            _settings(
                firecrawl_api_key="firecrawl-key",
                gemini_analysis_api_key="analysis",
            )
        )
        adapter._client_factory = lambda: FakeHttpClient(
            [
                FakeResponse(
                    {
                        "success": True,
                        "data": [
                            {
                                "title": "CN listing",
                                "url": "https://cn.example/item",
                                "description": "US$4 MOQ 100",
                            }
                        ],
                    }
                ),
                FakeResponse(
                    {
                        "success": True,
                        "data": [
                            {
                                "title": "TN sourcing",
                                "url": "https://tn-source.example/item",
                                "description": "prix gros 70 TND",
                            }
                        ],
                    }
                ),
                FakeResponse(
                    {
                        "success": True,
                        "data": [
                            {
                                "title": "TN retail",
                                "url": "https://tn.example/item",
                                "description": "89 TND",
                            }
                        ],
                    }
                ),
            ]
        )
        adapter.settings = adapter.settings.__class__(
            **{**adapter.settings.__dict__, "search_queries_per_region": 1}
        )

        evidence = await adapter.search("wireless earbuds")

        self.assertEqual(evidence.provider_api_calls, 3)
        self.assertEqual(evidence.raw_queries_count, 3)
        self.assertEqual(evidence.sources[0].region_hint, "china_sourcing")

    async def test_firecrawl_search_prioritizes_china_and_stops_after_cap(self) -> None:
        adapter = FirecrawlAdapter(
            _settings(
                firecrawl_api_key="firecrawl-key",
                gemini_analysis_api_key="analysis",
            )
        )
        fake_client = FakeHttpClient(
            [
                FakeResponse(
                    {
                        "success": True,
                        "data": {
                            "web": [
                                {
                                    "title": "CN listing",
                                    "url": "https://cn.example/item",
                                    "description": "US$4 MOQ 100",
                                }
                            ]
                        },
                    }
                )
            ]
        )
        adapter._client_factory = lambda: fake_client
        adapter.settings = adapter.settings.__class__(
            **{
                **adapter.settings.__dict__,
                "search_queries_per_region": 1,
                "max_raw_sources_per_provider": 1,
            }
        )

        evidence = await adapter.search("wireless earbuds")

        self.assertEqual(evidence.provider_api_calls, 1)
        self.assertEqual(evidence.raw_queries_count, 1)
        self.assertEqual(evidence.sources[0].region_hint, "china_sourcing")
        self.assertEqual(fake_client.calls[0][2]["json"]["location"], "China")

    async def test_firecrawl_errors_are_sanitized(self) -> None:
        adapter = FirecrawlAdapter(
            _settings(
                firecrawl_api_key="firecrawl-key",
                gemini_analysis_api_key="analysis",
            )
        )
        adapter._client_factory = lambda: FakeHttpClient(
            [FakeResponse({"success": False, "error": "leak me"}, status_code=500)]
        )
        adapter.settings = adapter.settings.__class__(
            **{**adapter.settings.__dict__, "search_queries_per_region": 1}
        )

        with self.assertRaises(ProviderAdapterError) as context:
            await adapter.search("wireless earbuds")

        self.assertEqual(str(context.exception), "Firecrawl + Gemini request failed.")
        self.assertNotIn("leak me", str(context.exception))

    async def test_dataforseo_normalizes_organic_items(self) -> None:
        adapter = DataForSEOAdapter(
            _settings(
                dataforseo_login="dfs-login",
                dataforseo_password="dfs-password",
                gemini_analysis_api_key="analysis",
            )
        )
        adapter._client_factory = lambda: FakeHttpClient(
            [
                FakeResponse(
                    {
                        "tasks": [
                            {
                                "result": [
                                    {
                                        "items": [
                                            {
                                                "type": "organic",
                                                "title": "CN listing",
                                                "url": "https://cn.example/item",
                                                "description": "US$4 MOQ 100",
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ),
                FakeResponse(
                    {
                        "tasks": [
                            {
                                "result": [
                                    {
                                        "items": [
                                            {
                                                "type": "organic",
                                                "title": "TN sourcing",
                                                "url": "https://tn-source.example/item",
                                                "description": "prix gros 70 TND",
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ),
                FakeResponse(
                    {
                        "tasks": [
                            {
                                "result": [
                                    {
                                        "items": [
                                            {
                                                "type": "organic",
                                                "title": "TN retail",
                                                "url": "https://tn.example/item",
                                                "description": "95 TND",
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ),
            ]
        )
        adapter.settings = adapter.settings.__class__(
            **{
                **adapter.settings.__dict__,
                "search_queries_per_region": 1,
                "search_results_per_query": 3,
            }
        )

        evidence = await adapter.search("wireless earbuds")

        self.assertEqual(evidence.provider_api_calls, 3)
        self.assertEqual(evidence.raw_queries_count, 3)
        self.assertEqual(len(evidence.sources), 3)
        self.assertEqual(evidence.sources[0].snippet, "US$4 MOQ 100")
        self.assertEqual(evidence.sources[0].region_hint, "china_sourcing")
        self.assertEqual(evidence.sources[1].region_hint, "tunisia_sourcing")
        self.assertEqual(evidence.sources[2].snippet, "95 TND")

    async def test_dataforseo_errors_are_sanitized(self) -> None:
        adapter = DataForSEOAdapter(
            _settings(
                dataforseo_login="dfs-login",
                dataforseo_password="dfs-password",
                gemini_analysis_api_key="analysis",
            )
        )
        adapter._client_factory = lambda: FakeHttpClient(
            [FakeResponse({"status_message": "bad auth"}, status_code=401)]
        )
        adapter.settings = adapter.settings.__class__(
            **{**adapter.settings.__dict__, "search_queries_per_region": 1}
        )

        with self.assertRaises(ProviderAdapterError) as context:
            await adapter.search("wireless earbuds")

        self.assertEqual(str(context.exception), "DataForSEO + Gemini request failed.")
        self.assertNotIn("bad auth", str(context.exception))
        self.assertNotIn("dfs-password", str(context.exception))

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

    async def test_scavio_missing_gemini_analysis_is_not_configured(self) -> None:
        adapter = ScavioAdapter(
            _settings(
                scavio_api_key="scavio-key",
                gemini_analysis_api_key="",
            )
        )

        with self.assertRaises(ProviderNotConfiguredError) as context:
            await adapter.search("lamp")

        self.assertIn("gemini_analysis_api_key", str(context.exception).lower())

    async def test_scavio_normalizes_google_results(self) -> None:
        adapter = ScavioAdapter(
            _settings(
                scavio_api_key="scavio-key",
                gemini_analysis_api_key="analysis",
            )
        )
        adapter._client_factory = lambda: FakeHttpClient(
            [
                FakeResponse(
                    {
                        "results": [
                            {
                                "title": "CN listing",
                                "url": "https://cn.example/item",
                                "content": "US$4 MOQ 100",
                                "position": 1,
                            }
                        ],
                        "credits_used": 1,
                    }
                ),
                FakeResponse(
                    {
                        "results": [
                            {
                                "title": "TN sourcing",
                                "url": "https://tn-source.example/item",
                                "content": "prix gros 70 TND",
                                "position": 1,
                            }
                        ],
                        "credits_used": 1,
                    }
                ),
                FakeResponse(
                    {
                        "results": [
                            {
                                "title": "TN retail",
                                "url": "https://tn.example/item",
                                "content": "95 TND",
                                "position": 1,
                            }
                        ],
                        "credits_used": 1,
                    }
                ),
            ]
        )
        adapter.settings = adapter.settings.__class__(
            **{
                **adapter.settings.__dict__,
                "search_queries_per_region": 1,
                "search_results_per_query": 3,
            }
        )

        evidence = await adapter.search("wireless earbuds")

        self.assertEqual(evidence.provider_api_calls, 3)
        self.assertEqual(evidence.raw_queries_count, 3)
        self.assertEqual(len(evidence.sources), 3)
        self.assertEqual(evidence.sources[0].snippet, "US$4 MOQ 100")
        self.assertEqual(evidence.sources[0].region_hint, "china_sourcing")
        self.assertEqual(evidence.sources[1].region_hint, "tunisia_sourcing")
        self.assertEqual(evidence.sources[2].snippet, "95 TND")

    async def test_scavio_search_prioritizes_china_and_stops_after_cap(self) -> None:
        adapter = ScavioAdapter(
            _settings(
                scavio_api_key="scavio-key",
                gemini_analysis_api_key="analysis",
            )
        )
        fake_client = FakeHttpClient(
            [
                FakeResponse(
                    {
                        "results": [
                            {
                                "title": "CN listing",
                                "url": "https://cn.example/item",
                                "content": "US$4 MOQ 100",
                                "position": 1,
                            }
                        ],
                        "credits_used": 1,
                    }
                )
            ]
        )
        adapter._client_factory = lambda: fake_client
        adapter.settings = adapter.settings.__class__(
            **{
                **adapter.settings.__dict__,
                "search_queries_per_region": 1,
                "max_raw_sources_per_provider": 1,
            }
        )

        evidence = await adapter.search("wireless earbuds")

        self.assertEqual(evidence.provider_api_calls, 1)
        self.assertEqual(evidence.sources[0].region_hint, "china_sourcing")
        self.assertEqual(fake_client.calls[0][2]["json"]["country_code"], "cn")

    async def test_scavio_errors_are_sanitized(self) -> None:
        adapter = ScavioAdapter(
            _settings(
                scavio_api_key="scavio-key",
                gemini_analysis_api_key="analysis",
            )
        )
        adapter._client_factory = lambda: FakeHttpClient(
            [FakeResponse({"error": "bad token"}, status_code=401)]
        )
        adapter.settings = adapter.settings.__class__(
            **{**adapter.settings.__dict__, "search_queries_per_region": 1}
        )

        with self.assertRaises(ProviderAdapterError) as context:
            await adapter.search("wireless earbuds")

        self.assertEqual(str(context.exception), "Scavio + Gemini request failed.")
        self.assertNotIn("bad token", str(context.exception))


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
