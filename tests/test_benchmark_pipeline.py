import asyncio
import unittest

from app.benchmark.pipeline import BenchmarkPipeline
from app.benchmark.providers.base import (
    ProviderAdapterError,
    ProviderNotConfiguredError,
    SearchProviderAdapter,
)
from app.benchmark.schemas import (
    ProviderAnalysisResult,
    ProviderEvidence,
    ProviderRawSource,
)
from app.config import Settings
from app.schemas import IntentResult


class RecordingIntentClient:
    def __init__(self, result: IntentResult) -> None:
        self.result = result
        self.calls = 0

    async def classify(self, product: str) -> IntentResult:
        self.calls += 1
        return self.result


class RecordingAnalysisClient:
    def __init__(self, result: ProviderAnalysisResult) -> None:
        self.result = result
        self.calls = 0

    async def extract(
        self,
        product: str,
        evidence: ProviderEvidence,
    ) -> ProviderAnalysisResult:
        self.calls += 1
        return self.result


class FakeAdapter(SearchProviderAdapter):
    provider_id = "fake"
    provider_name = "Fake + Gemini"
    requires_gemini_analysis = True
    production_risk = "medium"
    cost_notes = "Fake cost notes."

    async def search(self, product: str) -> ProviderEvidence:
        return ProviderEvidence(
            provider_id=self.provider_id,
            sources=[
                ProviderRawSource(
                    title="Listing",
                    url="https://example.com/item",
                    snippet="10 TND",
                )
            ],
            provider_api_calls=2,
            raw_queries_count=2,
        )


class FakePerplexityAdapter(SearchProviderAdapter):
    provider_id = "perplexity"
    provider_name = "Perplexity Sonar"
    requires_gemini_analysis = False
    production_risk = "medium"
    cost_notes = "One Perplexity request."

    async def analyze_direct(self, product: str) -> ProviderAnalysisResult:
        return ProviderAnalysisResult(market_summary="Perplexity result.")


class MissingAdapter(FakeAdapter):
    provider_id = "missing"
    provider_name = "Missing"

    async def search(self, product: str) -> ProviderEvidence:
        raise ProviderNotConfiguredError("Missing key.")


class FailingAdapter(FakeAdapter):
    provider_id = "failing"
    provider_name = "Failing"

    async def search(self, product: str) -> ProviderEvidence:
        raise ProviderAdapterError("Provider failed.")


class SlowAdapter(FakeAdapter):
    provider_id = "slow"
    provider_name = "Slow"

    async def search(self, product: str) -> ProviderEvidence:
        await asyncio.sleep(0.05)
        return await super().search(product)


class BenchmarkPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_intent_called_once_and_invalid_product_suppresses_providers(
        self,
    ) -> None:
        intent = RecordingIntentClient(
            IntentResult(
                is_valid_product=False,
                normalized_product=None,
                reason="Invalid.",
            )
        )
        adapter = FakeAdapter(_settings())
        pipeline = BenchmarkPipeline(
            intent,
            RecordingAnalysisClient(ProviderAnalysisResult()),
            {"fake": adapter},
            _settings(),
        )

        response = await pipeline.analyze("hello", ["fake"])

        self.assertEqual(intent.calls, 1)
        self.assertEqual(response.runs, [])
        self.assertFalse(response.intent.is_valid_product)

    async def test_gemini_analysis_used_for_evidence_provider(self) -> None:
        intent = RecordingIntentClient(
            IntentResult(
                is_valid_product=True,
                normalized_product="lamp",
                reason="Valid.",
            )
        )
        analysis = RecordingAnalysisClient(
            ProviderAnalysisResult(market_summary="Analyzed.")
        )
        pipeline = BenchmarkPipeline(
            intent,
            analysis,
            {"fake": FakeAdapter(_settings())},
            _settings(),
        )

        response = await pipeline.analyze("lamp", ["fake"])

        self.assertEqual(intent.calls, 1)
        self.assertEqual(analysis.calls, 1)
        self.assertEqual(response.runs[0].gemini_analysis_calls, 1)
        self.assertEqual(response.runs[0].provider_api_calls, 2)

    async def test_perplexity_does_not_use_gemini_analysis(self) -> None:
        intent = RecordingIntentClient(
            IntentResult(
                is_valid_product=True,
                normalized_product="lamp",
                reason="Valid.",
            )
        )
        analysis = RecordingAnalysisClient(
            ProviderAnalysisResult(market_summary="Should not be used.")
        )
        pipeline = BenchmarkPipeline(
            intent,
            analysis,
            {"perplexity": FakePerplexityAdapter(_settings())},
            _settings(),
        )

        response = await pipeline.analyze("lamp", ["perplexity"])

        self.assertEqual(analysis.calls, 0)
        self.assertEqual(response.runs[0].gemini_analysis_calls, 0)
        self.assertFalse(response.runs[0].uses_gemini_analysis)

    async def test_missing_failure_and_timeout_do_not_break_full_benchmark(
        self,
    ) -> None:
        intent = RecordingIntentClient(
            IntentResult(
                is_valid_product=True,
                normalized_product="lamp",
                reason="Valid.",
            )
        )
        settings = _settings(benchmark_provider_timeout_seconds=0.01)
        pipeline = BenchmarkPipeline(
            intent,
            RecordingAnalysisClient(ProviderAnalysisResult(market_summary="Analyzed.")),
            {
                "missing": MissingAdapter(settings),
                "failing": FailingAdapter(settings),
                "slow": SlowAdapter(settings),
            },
            settings,
        )

        response = await pipeline.analyze("lamp", ["missing", "failing", "slow"])
        statuses = {run.provider_id: run.status for run in response.runs}

        self.assertEqual(statuses["missing"], "not_configured")
        self.assertEqual(statuses["failing"], "failed")
        self.assertEqual(statuses["slow"], "timeout")


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
