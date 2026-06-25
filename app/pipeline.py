from __future__ import annotations

import asyncio

from app.schemas import (
    ChinaSupplierResearchResult,
    IntentResult,
    MarketResearchResult,
    ProductAnalysisResponse,
    ResearchSource,
    SupplierOption,
)
from app.services.gemini_search_client import GeminiSearchClientError


class PipelineError(RuntimeError):
    """Raised when the analysis pipeline cannot produce a valid result."""


class PipelineTimeoutError(PipelineError):
    """Raised when the analysis takes longer than the configured timeout."""


class ProductAnalysisPipeline:
    def __init__(
        self,
        intent_classifier,
        market_research_agent,
        china_supplier_research_agent,
        timeout_seconds: int = 45,
    ) -> None:
        self.intent_classifier = intent_classifier
        self.market_research_agent = market_research_agent
        self.china_supplier_research_agent = china_supplier_research_agent
        self.timeout_seconds = timeout_seconds

    async def analyze(
        self,
        product: str,
        category: str | None = None,
    ) -> ProductAnalysisResponse:
        trimmed_product = product.strip()
        if not trimmed_product:
            return _build_invalid_response(
                product="",
                reason="Product input cannot be empty.",
            )

        intent_result = await self.intent_classifier.classify(trimmed_product)
        if not intent_result.is_valid_product or not intent_result.normalized_product:
            return _build_invalid_response(
                product=trimmed_product,
                reason=intent_result.reason,
            )

        try:
            normalized_category = category.strip() if category else None
            regional_results = await asyncio.wait_for(
                asyncio.gather(
                    self.market_research_agent.research(
                        intent_result.normalized_product,
                        normalized_category,
                    ),
                    self.china_supplier_research_agent.research(
                        intent_result.normalized_product,
                        normalized_category,
                    ),
                    return_exceptions=True,
                ),
                timeout=self.timeout_seconds,
            )
        except TimeoutError as error:
            raise PipelineTimeoutError(
                "Analysis timed out before research completed."
            ) from error

        market_result, china_result = _resolve_regional_results(regional_results)
        warnings = _merge_warnings(
            market_result,
            china_result,
            _sourced_supplier_count(market_result.tunisia_suppliers),
            _sourced_supplier_count(china_result.china_suppliers),
        )

        return ProductAnalysisResponse(
            product=intent_result.normalized_product,
            is_valid_product=True,
            intent_reason=intent_result.reason,
            market_summary=market_result.market_summary,
            tunisia_suppliers=market_result.tunisia_suppliers[:3],
            china_suppliers=china_result.china_suppliers[:3],
            research_sources=_dedupe_sources(
                market_result.research_sources + china_result.research_sources
            ),
            warnings=warnings,
        )


def _build_invalid_response(product: str, reason: str) -> ProductAnalysisResponse:
    return ProductAnalysisResponse(
        product=product,
        is_valid_product=False,
        intent_reason=reason,
        market_summary="",
        tunisia_suppliers=[],
        china_suppliers=[],
        research_sources=[],
        warnings=[],
    )


def _resolve_regional_results(
    regional_results: list,
) -> tuple[MarketResearchResult, ChinaSupplierResearchResult]:
    market_value, china_value = regional_results
    _raise_unexpected_error(market_value)
    _raise_unexpected_error(china_value)
    if isinstance(market_value, GeminiSearchClientError) and isinstance(
        china_value,
        GeminiSearchClientError,
    ):
        raise PipelineError(
            "Gemini Search-grounded research failed for both regions."
        )
    market_result = (
        _failed_market_result(market_value)
        if isinstance(market_value, GeminiSearchClientError)
        else market_value
    )
    china_result = (
        _failed_china_result(china_value)
        if isinstance(china_value, GeminiSearchClientError)
        else china_value
    )
    return market_result, china_result


def _raise_unexpected_error(regional_value) -> None:
    if isinstance(regional_value, BaseException) and not isinstance(
        regional_value,
        GeminiSearchClientError,
    ):
        raise regional_value


def _failed_market_result(error: GeminiSearchClientError) -> MarketResearchResult:
    return MarketResearchResult(
        market_summary="Tunisia Search-grounded research was unavailable.",
        warnings=[f"Tunisia research failed: {error}"],
    )


def _failed_china_result(
    error: GeminiSearchClientError,
) -> ChinaSupplierResearchResult:
    return ChinaSupplierResearchResult(
        warnings=[f"China research failed: {error}"],
    )


def _merge_warnings(
    market_result: MarketResearchResult,
    china_result: ChinaSupplierResearchResult,
    tunisia_count: int,
    china_count: int,
) -> list[str]:
    warnings = list(dict.fromkeys(market_result.warnings + china_result.warnings))
    if tunisia_count < 3:
        warnings.append(
            "Not enough reliable Tunisia source-backed results were found; fewer than 3 options were returned."
        )
    if china_count < 3:
        warnings.append(
            "Not enough reliable China source-backed results were found; fewer than 3 options were returned."
        )
    warnings.append(
        "Prices, MOQ, stock, and availability must be confirmed directly with suppliers before purchase."
    )
    return list(dict.fromkeys(warnings))


def _sourced_supplier_count(suppliers: list[SupplierOption]) -> int:
    return sum(1 for supplier in suppliers if supplier.source_url)


def _dedupe_sources(sources: list[ResearchSource]) -> list[ResearchSource]:
    unique_sources: dict[str, ResearchSource] = {}
    for source in sources:
        unique_sources.setdefault(source.url, source)
    return list(unique_sources.values())
