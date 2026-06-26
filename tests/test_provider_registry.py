import unittest

from app.benchmark.providers import build_provider_registry
from app.config import Settings


class ProviderRegistryTests(unittest.TestCase):
    def test_all_expected_providers_are_registered(self) -> None:
        registry = build_provider_registry(_settings())

        self.assertEqual(
            list(registry.keys()),
            [
                "serper",
                "brave",
                "exa",
                "firecrawl",
                "searxng",
                "perplexity",
                "scavio",
                "dataforseo",
            ],
        )

    def test_missing_provider_keys_return_not_configured_status(self) -> None:
        registry = build_provider_registry(_settings())

        serper = registry["serper"]
        info = serper.info()

        self.assertFalse(info.configured)
        self.assertIn("SERPER_API_KEY", info.missing_config)
        self.assertIn("GEMINI_ANALYSIS_API_KEY", info.missing_config)

    def test_perplexity_does_not_require_gemini_analysis(self) -> None:
        registry = build_provider_registry(
            _settings(perplexity_api_key="perplexity-key")
        )
        info = registry["perplexity"].info()

        self.assertTrue(info.configured)
        self.assertFalse(info.requires_gemini_analysis)
        self.assertNotIn("GEMINI_ANALYSIS_API_KEY", info.missing_config)

    def test_firecrawl_reports_limited_behavior_without_standalone_search_support(
        self,
    ) -> None:
        registry = build_provider_registry(
            _settings(
                firecrawl_api_key="firecrawl-key",
                gemini_analysis_api_key="analysis-key",
            )
        )
        info = registry["firecrawl"].info()

        self.assertFalse(info.enabled)
        self.assertFalse(info.configured)
        self.assertIn("content extraction layer", " ".join(info.warnings).lower())


def _settings(**overrides) -> Settings:
    values = dict(
        gemini_intent_api_key="intent-key",
        gemini_intent_model="gemini-3.1-flash-lite",
        gemini_analysis_api_key="",
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
