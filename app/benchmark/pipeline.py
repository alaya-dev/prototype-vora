from __future__ import annotations

import asyncio
import time

from app.benchmark.comparison import build_comparison_summary
from app.benchmark.providers.base import (
    ProviderAdapterError,
    ProviderNotConfiguredError,
)
from app.benchmark.schemas import (
    BenchmarkAnalyzeResponse,
    BenchmarkComparisonSummary,
    BenchmarkProviderRun,
    ProviderAnalysisResult,
    ProviderEvidence,
)
from app.benchmark.validation import validate_provider_result
from app.config import Settings
from app.schemas import IntentResult


class BenchmarkPipeline:
    def __init__(
        self,
        intent_client,
        analysis_client,
        providers: dict[str, object],
        settings: Settings,
    ) -> None:
        self.intent_client = intent_client
        self.analysis_client = analysis_client
        self.providers = providers
        self.settings = settings

    async def analyze(
        self,
        product: str,
        provider_ids: list[str],
    ) -> BenchmarkAnalyzeResponse:
        trimmed_product = product.strip()
        if not trimmed_product:
            intent = IntentResult(
                is_valid_product=False,
                normalized_product=None,
                reason="Product input cannot be empty.",
            )
        else:
            intent = await self.intent_client.classify(trimmed_product)

        if not intent.is_valid_product or not intent.normalized_product:
            return BenchmarkAnalyzeResponse(
                product=trimmed_product,
                normalized_product="",
                intent=intent,
                runs=[],
                comparison_summary=BenchmarkComparisonSummary(
                    notes="Product was invalid; provider calls were skipped."
                ),
            )

        selected_ids = provider_ids or list(self.providers.keys())
        semaphore = asyncio.Semaphore(self.settings.benchmark_max_providers_parallel)
        tasks = [
            self._run_with_semaphore(semaphore, provider_id, intent.normalized_product)
            for provider_id in selected_ids
        ]
        runs = await asyncio.gather(*tasks)
        return BenchmarkAnalyzeResponse(
            product=trimmed_product,
            normalized_product=intent.normalized_product,
            intent=intent,
            runs=runs,
            comparison_summary=build_comparison_summary(runs),
        )

    async def _run_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        provider_id: str,
        product: str,
    ) -> BenchmarkProviderRun:
        async with semaphore:
            return await self._run_provider(provider_id, product)

    async def _run_provider(
        self,
        provider_id: str,
        product: str,
    ) -> BenchmarkProviderRun:
        provider = self.providers.get(provider_id)
        if provider is None:
            return BenchmarkProviderRun(
                provider_id=provider_id,
                provider_name=provider_id,
                status="disabled",
                gemini_intent_calls=1,
                production_risk="high",
                errors=[f"Unknown provider: {provider_id}"],
            )

        started = time.perf_counter()
        try:
            analysis, evidence, gemini_analysis_calls = await asyncio.wait_for(
                self._collect_provider_analysis(provider, product),
                timeout=self.settings.benchmark_provider_timeout_seconds,
            )
            validated = validate_provider_result(analysis, evidence.sources)
            status = "success"
            if (
                validated.warnings
                or len(validated.tunisia_cheapest_suppliers) < 3
                or len(validated.china_cheapest_suppliers) < 3
            ):
                status = "partial"
            return self._build_run(
                provider,
                status,
                started,
                evidence,
                validated,
                gemini_analysis_calls,
            )
        except asyncio.TimeoutError:
            return self._error_run(
                provider,
                "timeout",
                started,
                "Provider timed out before returning usable evidence.",
            )
        except ProviderNotConfiguredError as error:
            return self._error_run(provider, "not_configured", started, str(error))
        except ProviderAdapterError as error:
            return self._error_run(provider, "failed", started, str(error))

    async def _collect_provider_analysis(
        self,
        provider,
        product: str,
    ) -> tuple[ProviderAnalysisResult, ProviderEvidence, int]:
        if not getattr(provider, "requires_gemini_analysis", True):
            analysis = await provider.analyze_direct(product)
            evidence = ProviderEvidence(
                provider_id=provider.provider_id,
                provider_api_calls=1,
            )
            return analysis, evidence, 0

        evidence = await provider.search(product)
        analysis = await self.analysis_client.extract(product, evidence)
        return analysis, evidence, 1

    def _build_run(
        self,
        provider,
        status: str,
        started: float,
        evidence: ProviderEvidence,
        analysis: ProviderAnalysisResult,
        gemini_analysis_calls: int,
    ) -> BenchmarkProviderRun:
        return BenchmarkProviderRun(
            provider_id=provider.provider_id,
            provider_name=provider.provider_name,
            status=status,
            uses_gemini_intent=True,
            uses_gemini_analysis=provider.requires_gemini_analysis,
            latency_ms=_elapsed_ms(started),
            raw_sources_count=len(evidence.sources),
            provider_api_calls=evidence.provider_api_calls,
            gemini_intent_calls=1,
            gemini_analysis_calls=gemini_analysis_calls,
            raw_queries_count=evidence.raw_queries_count,
            cost_notes=provider.cost_notes,
            production_risk=provider.production_risk,
            market_summary=analysis.market_summary,
            tunisia_cheapest_suppliers=analysis.tunisia_cheapest_suppliers,
            china_cheapest_suppliers=analysis.china_cheapest_suppliers,
            research_sources=analysis.research_sources,
            raw_sources=evidence.sources,
            warnings=list(dict.fromkeys(evidence.warnings + analysis.warnings)),
            errors=evidence.errors,
        )

    def _error_run(
        self,
        provider,
        status: str,
        started: float,
        error: str,
    ) -> BenchmarkProviderRun:
        return BenchmarkProviderRun(
            provider_id=provider.provider_id,
            provider_name=provider.provider_name,
            status=status,
            uses_gemini_intent=True,
            uses_gemini_analysis=provider.requires_gemini_analysis,
            latency_ms=_elapsed_ms(started),
            provider_api_calls=0,
            gemini_intent_calls=1,
            gemini_analysis_calls=0,
            cost_notes=provider.cost_notes,
            production_risk=provider.production_risk,
            warnings=list(getattr(provider, "limitation_warnings", [])),
            errors=[error],
        )


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))
