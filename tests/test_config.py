import os
import unittest
from unittest.mock import patch

from app.config import Settings, SettingsError


class SettingsTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    @patch("app.config.load_dotenv")
    def test_missing_provider_keys_do_not_prevent_settings_load(self, _load_dotenv_mock) -> None:
        settings = Settings.from_env()

        self.assertEqual(settings.gemini_intent_api_key, "")
        self.assertEqual(settings.gemini_analysis_api_key, "")
        self.assertEqual(settings.benchmark_provider_timeout_seconds, 45)
        self.assertEqual(settings.benchmark_max_providers_parallel, 8)
        self.assertEqual(settings.search_results_per_query, 10)
        self.assertEqual(settings.search_queries_per_region, 4)
        self.assertEqual(settings.max_raw_sources_per_provider, 20)

    @patch.dict(
        os.environ,
        {
            "GEMINI_INTENT_API_KEY": "intent-key",
            "GEMINI_INTENT_MODEL": "gemini-intent",
            "GEMINI_ANALYSIS_API_KEY": "analysis-key",
            "GEMINI_ANALYSIS_MODEL": "gemini-analysis",
            "SERPER_API_KEY": "serper-key",
            "BRAVE_SEARCH_API_KEY": "brave-key",
            "EXA_API_KEY": "exa-key",
            "FIRECRAWL_API_KEY": "firecrawl-key",
            "PERPLEXITY_API_KEY": "perplexity-key",
            "SEARXNG_BASE_URL": "https://search.example",
            "SCAVIO_API_KEY": "scavio-key",
            "SCAVIO_BASE_URL": "https://scavio.example",
            "DATAFORSEO_LOGIN": "login",
            "DATAFORSEO_PASSWORD": "password",
            "BENCHMARK_PROVIDER_TIMEOUT_SECONDS": "30",
            "BENCHMARK_MAX_PROVIDERS_PARALLEL": "3",
            "SEARCH_RESULTS_PER_QUERY": "7",
            "SEARCH_QUERIES_PER_REGION": "2",
            "MAX_RAW_SOURCES_PER_PROVIDER": "11",
        },
        clear=True,
    )
    def test_benchmark_environment_values_are_loaded(self) -> None:
        settings = Settings.from_env()

        self.assertEqual(settings.gemini_intent_api_key, "intent-key")
        self.assertEqual(settings.gemini_intent_model, "gemini-intent")
        self.assertEqual(settings.gemini_analysis_api_key, "analysis-key")
        self.assertEqual(settings.gemini_analysis_model, "gemini-analysis")
        self.assertEqual(settings.serper_api_key, "serper-key")
        self.assertEqual(settings.brave_search_api_key, "brave-key")
        self.assertEqual(settings.exa_api_key, "exa-key")
        self.assertEqual(settings.firecrawl_api_key, "firecrawl-key")
        self.assertEqual(settings.perplexity_api_key, "perplexity-key")
        self.assertEqual(settings.searxng_base_url, "https://search.example")
        self.assertEqual(settings.scavio_api_key, "scavio-key")
        self.assertEqual(settings.scavio_base_url, "https://scavio.example")
        self.assertEqual(settings.dataforseo_login, "login")
        self.assertEqual(settings.dataforseo_password, "password")
        self.assertEqual(settings.benchmark_provider_timeout_seconds, 30)
        self.assertEqual(settings.benchmark_max_providers_parallel, 3)
        self.assertEqual(settings.search_results_per_query, 7)
        self.assertEqual(settings.search_queries_per_region, 2)
        self.assertEqual(settings.max_raw_sources_per_provider, 11)

    @patch.dict(os.environ, {"BENCHMARK_MAX_PROVIDERS_PARALLEL": "not-an-integer"}, clear=True)
    @patch("app.config.load_dotenv")
    def test_invalid_integer_settings_raise_clear_error(self, _load_dotenv_mock) -> None:
        with self.assertRaises(SettingsError) as context:
            Settings.from_env()

        self.assertIn("BENCHMARK_MAX_PROVIDERS_PARALLEL", str(context.exception))
