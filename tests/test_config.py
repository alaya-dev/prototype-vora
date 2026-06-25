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
        self.assertNotIn("TAVILY_API_KEY", message)

    @patch.dict(
        os.environ,
        {
            "GEMINI_API_KEY": "test-gemini-key",
            "GEMINI_MODEL": "gemini-3.1-flash-lite",
            "ANALYSIS_TIMEOUT_SECONDS": "45",
        },
        clear=True,
    )
    def test_environment_values_are_loaded(self) -> None:
        settings = Settings.from_env()

        self.assertEqual(settings.gemini_model, "gemini-3.1-flash-lite")
        self.assertEqual(settings.analysis_timeout_seconds, 45)

    @patch.dict(
        os.environ,
        {"GEMINI_API_KEY": "test-gemini-key"},
        clear=True,
    )
    @patch("app.config.load_dotenv")
    def test_default_model_is_gemini_3_1_flash_lite(self, _load_dotenv_mock) -> None:
        settings = Settings.from_env()

        self.assertEqual(settings.gemini_model, "gemini-3.1-flash-lite")
