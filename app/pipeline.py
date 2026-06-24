from __future__ import annotations

import asyncio

from app.schemas import (
    ChinaSupplierResearchResult,
    IntentResult,
    MarketResearchResult,
    ProductAnalysisResponse,
    ResearchSource,
)


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
            market_result, china_result = await asyncio.wait_for(
                asyncio.gather(
                    self.market_research_agent.research(
                        intent_result.normalized_product,
                        normalized_category,
                    ),
                    self.china_supplier_research_agent.research(
                        intent_result.normalized_product,
                        normalized_category,
                    ),
                ),
                timeout=self.timeout_seconds,
            )
        except TimeoutError as error:
            raise PipelineTimeoutError(
                "Analysis timed out before research completed."
            ) from error

        warnings = _merge_warnings(
            market_result,
            china_result,
            len(market_result.tunisia_suppliers),
            len(china_result.china_suppliers),
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


def _dedupe_sources(sources: list[ResearchSource]) -> list[ResearchSource]:
    unique_sources: dict[str, ResearchSource] = {}
    for source in sources:
        unique_sources.setdefault(source.url, source)
    return list(unique_sources.values())
