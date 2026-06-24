import unittest

from app.agents.intent_classifier import IntentClassificationPayload
from app.services.gemini_client import (
    _build_gemini_error_message,
    _build_gemini_response_schema,
    _is_retryable_gemini_error,
)


class GeminiSchemaTests(unittest.TestCase):
    def test_gemini_schema_strips_additional_properties_recursively(self) -> None:
        schema = _build_gemini_response_schema(IntentClassificationPayload)

        serialized_schema = str(schema)
        self.assertNotIn("additionalProperties", serialized_schema)
        self.assertIn("properties", schema)

    def test_retryable_server_message_is_exposed_clearly(self) -> None:
        class FakeServerError(Exception):
            status_code = 503

            def __str__(self) -> str:
                return "503 UNAVAILABLE. {'error': {'message': 'This model is currently experiencing high demand.'}}"

        message = _build_gemini_error_message(FakeServerError())

        self.assertIn("temporarily unavailable", message.lower())
        self.assertIn("503", message)

    def test_retryable_server_message_can_be_inferred_from_text(self) -> None:
        class FakeServerError(Exception):
            def __str__(self) -> str:
                return "503 UNAVAILABLE. model overloaded"

        self.assertIn(
            "temporarily unavailable",
            _build_gemini_error_message(FakeServerError()).lower(),
        )

    def test_daily_quota_error_is_not_retried_and_has_clear_message(self) -> None:
        class DailyQuotaError(Exception):
            status_code = 429

            def __str__(self) -> str:
                return (
                    "Quota exceeded for metric: generate_content_free_tier_requests. "
                    "quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier"
                )

        error = DailyQuotaError()

        self.assertFalse(_is_retryable_gemini_error(error))
        message = _build_gemini_error_message(error)
        self.assertIn("daily free-tier quota", message.lower())
        self.assertIn("billing", message.lower())
