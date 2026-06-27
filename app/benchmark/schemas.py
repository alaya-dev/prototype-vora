from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas import IntentResult, StrictModel


ProviderRunStatus = Literal["success", "partial", "failed", "not_configured", "disabled", "timeout"]
ProductionRisk = Literal["low", "medium", "high"]
EvidenceLevel = Literal["direct", "indirect", "weak"]
EvidenceField = Literal["direct", "snippet", "not_found"]
Confidence = Literal["high", "medium", "low"]
ProductMatch = Literal["exact", "close", "broad", "weak"]
RegionHint = Literal["tunisia", "china", "unknown"]
RawSourceType = Literal["search_result", "product_page", "supplier_profile", "marketplace", "unknown"]


class BenchmarkAnalyzeRequest(StrictModel):
    product: str = Field(default="", max_length=200)
    providers: list[str] = Field(default_factory=list)


class ProviderRawSource(StrictModel):
    title: str = ""
    url: str = ""
    snippet: str = ""
    content: str | None = None
    region_hint: RegionHint = "unknown"
    source_type: RawSourceType = "unknown"


class ProviderEvidence(StrictModel):
    provider_id: str
    sources: list[ProviderRawSource] = Field(default_factory=list)
    raw_queries_count: int = 0
    provider_api_calls: int = 0
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class BenchmarkResearchSource(StrictModel):
    title: str = ""
    url: str
    source_type: RawSourceType = "unknown"


class TunisiaBenchmarkSupplier(StrictModel):
    rank: int = 0
    name: str
    type: Literal["marketplace", "local_provider", "seller", "source", "unknown"] = "unknown"
    product_title: str | None = None
    price_range_tnd: str | None = None
    price_min_tnd_numeric: float | None = None
    price_max_tnd_numeric: float | None = None
    source_url: str = ""
    evidence_level: EvidenceLevel = "weak"
    price_evidence: EvidenceField = "not_found"
    confidence: Confidence = "low"
    product_match: ProductMatch = "broad"
    match_notes: str = ""
    notes: str = ""


class ChinaBenchmarkSupplier(StrictModel):
    rank: int = 0
    name: str
    type: Literal["manufacturer", "trading_company", "marketplace_source", "supplier_profile", "unknown"] = "unknown"
    product_title: str | None = None
    price_range_usd: str | None = None
    price_min_usd_numeric: float | None = None
    price_max_usd_numeric: float | None = None
    moq: str | None = None
    moq_numeric: float | None = None
    source_url: str = ""
    evidence_level: EvidenceLevel = "weak"
    price_evidence: EvidenceField = "not_found"
    moq_evidence: EvidenceField = "not_found"
    confidence: Confidence = "low"
    product_match: ProductMatch = "broad"
    match_notes: str = ""
    notes: str = ""


class MissingData(StrictModel):
    tunisia: str = ""
    china: str = ""


class ProviderAnalysisResult(StrictModel):
    market_summary: str = ""
    tunisia_cheapest_suppliers: list[TunisiaBenchmarkSupplier] = Field(default_factory=list)
    china_cheapest_suppliers: list[ChinaBenchmarkSupplier] = Field(default_factory=list)
    research_sources: list[BenchmarkResearchSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    data_quality_notes: str = ""
    missing_data: MissingData = Field(default_factory=MissingData)


class ProviderInfo(StrictModel):
    provider_id: str
    provider_name: str
    configured: bool
    enabled: bool = True
    requires_gemini_analysis: bool
    production_risk: ProductionRisk
    missing_config: list[str] = Field(default_factory=list)
    cost_notes: str = ""
    warnings: list[str] = Field(default_factory=list)


class ProvidersResponse(StrictModel):
    providers: list[ProviderInfo]
    global_missing_config: list[str] = Field(default_factory=list)


class BenchmarkProviderRun(StrictModel):
    provider_id: str
    provider_name: str
    status: ProviderRunStatus
    uses_gemini_intent: bool = True
    uses_gemini_analysis: bool = False
    latency_ms: int = 0
    raw_sources_count: int = 0
    provider_api_calls: int = 0
    gemini_intent_calls: int = 0
    gemini_analysis_calls: int = 0
    raw_queries_count: int = 0
    cost_notes: str = ""
    production_risk: ProductionRisk
    market_summary: str = ""
    tunisia_cheapest_suppliers: list[TunisiaBenchmarkSupplier] = Field(default_factory=list)
    china_cheapest_suppliers: list[ChinaBenchmarkSupplier] = Field(default_factory=list)
    research_sources: list[BenchmarkResearchSource] = Field(default_factory=list)
    raw_sources: list[ProviderRawSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class BenchmarkComparisonSummary(StrictModel):
    fastest_provider: str | None = None
    most_tunisian_results: str | None = None
    most_chinese_results: str | None = None
    most_source_backed_prices: str | None = None
    most_complete_provider: str | None = None
    lowest_cost_risk: str | None = None
    notes: str = ""


class BenchmarkAnalyzeResponse(StrictModel):
    product: str
    normalized_product: str = ""
    intent: IntentResult
    runs: list[BenchmarkProviderRun] = Field(default_factory=list)
    comparison_summary: BenchmarkComparisonSummary = Field(default_factory=BenchmarkComparisonSummary)
