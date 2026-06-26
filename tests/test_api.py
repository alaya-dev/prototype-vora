import importlib
import unittest

from fastapi.testclient import TestClient

from app.benchmark.schemas import (
    BenchmarkAnalyzeResponse,
    BenchmarkComparisonSummary,
    BenchmarkProviderRun,
    ProviderInfo,
    ProvidersResponse,
)
from app.config import Settings
from app.schemas import IntentResult, ProductAnalysisResponse


class StubBenchmarkPipeline:
    def __init__(self, response: BenchmarkAnalyzeResponse) -> None:
        self.response = response
        self.calls = []

    async def analyze(
        self,
        product: str,
        providers: list[str],
    ) -> BenchmarkAnalyzeResponse:
        self.calls.append((product, providers))
        return self.response


class StubLegacyPipeline:
    def __init__(self) -> None:
        self.calls = []

    async def analyze(
        self,
        product: str,
        category: str | None = None,
    ) -> ProductAnalysisResponse:
        self.calls.append((product, category))
        return ProductAnalysisResponse(
            product=product,
            is_valid_product=False,
            intent_reason="Compatibility route.",
            market_summary="",
        )


class ApiTests(unittest.TestCase):
    def test_providers_returns_status_without_secrets(self) -> None:
        server_module = importlib.import_module("server")
        app = server_module.create_app(
            settings=_settings(),
            benchmark_pipeline=_benchmark_pipeline(),
            provider_infos=ProvidersResponse(
                providers=[
                    ProviderInfo(
                        provider_id="brave",
                        provider_name="Brave Search + Gemini",
                        configured=False,
                        requires_gemini_analysis=True,
                        production_risk="medium",
                        missing_config=["BRAVE_SEARCH_API_KEY"],
                    )
                ],
                global_missing_config=["GEMINI_INTENT_API_KEY"],
            ),
        )
        response = TestClient(app).get("/providers")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["providers"][0]["missing_config"], ["BRAVE_SEARCH_API_KEY"])
        self.assertNotIn("key-value", str(body).lower())

    def test_benchmark_analyze_forwards_product_and_providers(self) -> None:
        server_module = importlib.import_module("server")
        pipeline = _benchmark_pipeline()
        app = server_module.create_app(
            settings=_settings(),
            benchmark_pipeline=pipeline,
            provider_infos=ProvidersResponse(providers=[]),
        )

        response = TestClient(app).post(
            "/benchmark/analyze",
            json={"product": "Vintage T9", "providers": ["brave"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(pipeline.calls, [("Vintage T9", ["brave"])])
        self.assertEqual(response.json()["intent"]["is_valid_product"], True)

    def test_old_analyze_route_stays_available_for_compatibility(self) -> None:
        server_module = importlib.import_module("server")
        legacy = StubLegacyPipeline()
        app = server_module.create_app(
            settings=_settings(),
            pipeline=legacy,
            benchmark_pipeline=_benchmark_pipeline(),
            provider_infos=ProvidersResponse(providers=[]),
        )

        response = TestClient(app).post("/analyze", json={"product": "hello"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(legacy.calls, [("hello", None)])

    def test_benchmark_response_contains_usage_fields(self) -> None:
        server_module = importlib.import_module("server")
        app = server_module.create_app(
            settings=_settings(),
            benchmark_pipeline=_benchmark_pipeline(),
            provider_infos=ProvidersResponse(providers=[]),
        )

        response = TestClient(app).post(
            "/benchmark/analyze",
            json={"product": "Vintage T9", "providers": ["brave"]},
        )
        run = response.json()["runs"][0]

        self.assertIn("provider_api_calls", run)
        self.assertIn("gemini_intent_calls", run)
        self.assertIn("gemini_analysis_calls", run)
        self.assertIn("raw_queries_count", run)
        self.assertIn("cost_notes", run)
        self.assertIn("production_risk", run)


def _benchmark_pipeline() -> StubBenchmarkPipeline:
    return StubBenchmarkPipeline(
        BenchmarkAnalyzeResponse(
            product="Vintage T9",
            normalized_product="Vintage T9",
            intent=IntentResult(
                is_valid_product=True,
                normalized_product="Vintage T9",
                reason="Valid.",
            ),
            runs=[
                BenchmarkProviderRun(
                    provider_id="brave",
                    provider_name="Brave Search + Gemini",
                    status="success",
                    production_risk="medium",
                )
            ],
            comparison_summary=BenchmarkComparisonSummary(
                notes="Directional comparison."
            ),
        )
    )


def _settings() -> Settings:
    return Settings(
        gemini_intent_api_key="intent-key",
        gemini_intent_model="gemini-3.1-flash-lite",
        gemini_analysis_api_key="analysis-key",
        gemini_analysis_model="gemini-3.1-flash-lite",
        gemini_api_key="test-gemini",
        gemini_model="gemini-3.1-flash-lite",
        analysis_timeout_seconds=45,
        benchmark_provider_timeout_seconds=45,
        benchmark_max_providers_parallel=8,
        search_results_per_query=10,
        search_queries_per_region=4,
        max_raw_sources_per_provider=20,
    )
