import unittest

from pydantic import ValidationError

from app.benchmark.schemas import (
    BenchmarkAnalyzeRequest,
    BenchmarkProviderRun,
    ProviderRawSource,
)


class BenchmarkSchemaTests(unittest.TestCase):
    def test_provider_run_includes_usage_and_cost_fields(self) -> None:
        run = BenchmarkProviderRun(
            provider_id="brave",
            provider_name="Brave Search + Gemini",
            status="success",
            uses_gemini_intent=True,
            uses_gemini_analysis=True,
            latency_ms=123,
            raw_sources_count=4,
            provider_api_calls=8,
            gemini_intent_calls=1,
            gemini_analysis_calls=1,
            raw_queries_count=8,
            cost_notes="Search API calls plus one Gemini extraction.",
            production_risk="medium",
            market_summary="Evidence found.",
        )

        dumped = run.model_dump()
        self.assertEqual(dumped["provider_api_calls"], 8)
        self.assertEqual(dumped["gemini_intent_calls"], 1)
        self.assertEqual(dumped["gemini_analysis_calls"], 1)
        self.assertEqual(dumped["production_risk"], "medium")

    def test_invalid_provider_status_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            BenchmarkProviderRun(
                provider_id="brave",
                provider_name="Brave Search + Gemini",
                status="unknown",
                production_risk="medium",
            )

    def test_raw_source_supports_expandable_frontend_evidence(self) -> None:
        source = ProviderRawSource(
            title="Listing",
            url="https://example.com/item",
            snippet="Price 12 TND",
            region_hint="tunisia",
            source_type="search_result",
        )

        self.assertEqual(source.content, None)
        self.assertEqual(source.region_hint, "tunisia")

    def test_request_defaults_to_all_providers_when_not_supplied(self) -> None:
        request = BenchmarkAnalyzeRequest(product="Vintage T9")

        self.assertEqual(request.product, "Vintage T9")
        self.assertEqual(request.providers, [])
