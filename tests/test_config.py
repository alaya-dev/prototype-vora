import os
import unittest
from unittest.mock import patch


from app.config import Settings, SettingsError


class SettingsTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    @patch("app.config.load_dotenv")
    def test_missing_required_keys_raise_clear_error(self, _load_dotenv_mock) -> None:
        with self.assertRaises(SettingsError) as context:
            Settings.from_env()

        message = str(context.exception)
        self.assertIn("GEMINI_API_KEY", message)
        self.assertIn("TAVILY_API_KEY", message)

    @patch.dict(
        os.environ,
        {
            "GEMINI_API_KEY": "test-gemini-key",
            "TAVILY_API_KEY": "test-tavily-key",
            "GEMINI_MODEL": "gemini-2.5-flash-lite",
            "TAVILY_MAX_RESULTS": "8",
            "TAVILY_MAX_QUERIES_PER_REGION": "4",
            "ANALYSIS_TIMEOUT_SECONDS": "45",
        },
        clear=True,
    )
    def test_environment_values_are_loaded(self) -> None:
        settings = Settings.from_env()

        self.assertEqual(settings.gemini_model, "gemini-2.5-flash-lite")
        self.assertEqual(settings.tavily_max_results, 8)
        self.assertEqual(settings.tavily_max_queries_per_region, 4)
        self.assertEqual(settings.analysis_timeout_seconds, 45)
