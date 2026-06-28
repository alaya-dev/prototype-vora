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
RegionHint = Literal[
    "china_sourcing",
    "tunisia_sourcing",
    "tunisia_retail",
    "tunisia",
    "china",
    "unknown",
]
RawSourceType = Literal["search_result", "product_page", "supplier_profile", "marketplace", "unknown"]
SellerDensity = Literal["low", "medium", "high", "unknown"]


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


class TunisiaSourcingOffer(StrictModel):
    rank: int = 0
    name: str
    type: Literal["wholesaler", "importer", "distributor", "manufacturer", "b2b_seller", "marketplace_source", "unknown"] = "unknown"
    product_title: str | None = None
    price_range_tnd: str | None = None
    price_min_tnd_numeric: float | None = None
    price_max_tnd_numeric: float | None = None
    source_url: str = ""
    evidence_level: EvidenceLevel = "weak"
    price_evidence: EvidenceField = "not_found"
    product_match: ProductMatch = "broad"
    match_notes: str = ""
    confidence: Confidence = "low"
    notes: str = ""


class ChinaSourcingOffer(StrictModel):
    rank: int = 0
    name: str
    type: Literal["manufacturer", "trading_company", "marketplace_source", "supplier_profile", "factory", "unknown"] = "unknown"
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


class ChinaBenchmarkSupplier(ChinaSourcingOffer):
    type: Literal["manufacturer", "trading_company", "marketplace_source", "supplier_profile", "unknown"] = "unknown"


class TunisiaRetailOffer(StrictModel):
    rank: int = 0
    seller_name: str
    seller_type: Literal["marketplace", "local_shop", "retail_store", "classified", "social_listing", "unknown"] = "unknown"
    product_title: str | None = None
    price_range_tnd: str | None = None
    price_min_tnd_numeric: float | None = None
    price_max_tnd_numeric: float | None = None
    source_url: str = ""
    evidence_level: EvidenceLevel = "weak"
    price_evidence: EvidenceField = "not_found"
    product_match: ProductMatch = "broad"
    match_notes: str = ""
    confidence: Confidence = "low"
    notes: str = ""


class TunisiaRetailMarket(StrictModel):
    retail_offers: list[TunisiaRetailOffer] = Field(default_factory=list)
    price_min_tnd: float | None = None
    price_max_tnd: float | None = None
    price_avg_tnd: float | None = None
    unique_sellers_count: int = 0
    retail_sources_count: int = 0
    seller_density: SellerDensity = "unknown"
    competition_notes: str = ""
    availability_notes: str = ""


class MissingData(StrictModel):
    tunisia: str = ""
    china: str = ""
    china_sourcing: str = ""
    tunisia_sourcing: str = ""
    tunisia_retail: str = ""


class ProviderAnalysisResult(StrictModel):
    market_summary: str = ""
    china_sourcing_offers: list[ChinaSourcingOffer] = Field(default_factory=list)
    tunisia_sourcing_offers: list[TunisiaSourcingOffer] = Field(default_factory=list)
    tunisia_retail_market: TunisiaRetailMarket = Field(default_factory=TunisiaRetailMarket)
    tunisia_cheapest_suppliers: list[TunisiaBenchmarkSupplier] = Field(default_factory=list)
    china_cheapest_suppliers: list[ChinaBenchmarkSupplier] = Field(default_factory=list)
    research_sources: list[BenchmarkResearchSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    data_quality_notes: str = ""
    missing_data: MissingData = Field(default_factory=MissingData)

    def model_post_init(self, __context) -> None:
        if not self.china_sourcing_offers and self.china_cheapest_suppliers:
            self.china_sourcing_offers = [
                ChinaSourcingOffer.model_validate(offer.model_dump())
                for offer in self.china_cheapest_suppliers
            ]
        if not self.china_cheapest_suppliers and self.china_sourcing_offers:
            self.china_cheapest_suppliers = [
                ChinaBenchmarkSupplier.model_validate(
                    _model_dump_with_supported_type(
                        offer,
                        {"manufacturer", "trading_company", "marketplace_source", "supplier_profile", "unknown"},
                    )
                )
                for offer in self.china_sourcing_offers
            ]
        if not self.tunisia_sourcing_offers and self.tunisia_cheapest_suppliers:
            self.tunisia_sourcing_offers = [
                TunisiaSourcingOffer.model_validate(
                    _model_dump_with_supported_type(
                        offer,
                        {"wholesaler", "importer", "distributor", "manufacturer", "b2b_seller", "marketplace_source", "unknown"},
                    )
                )
                for offer in self.tunisia_cheapest_suppliers
            ]
        if not self.tunisia_cheapest_suppliers and self.tunisia_sourcing_offers:
            self.tunisia_cheapest_suppliers = [
                TunisiaBenchmarkSupplier.model_validate(
                    _model_dump_with_supported_type(
                        offer,
                        {"marketplace", "local_provider", "seller", "source", "unknown"},
                    )
                )
                for offer in self.tunisia_sourcing_offers
            ]


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
    china_sourcing_offers: list[ChinaSourcingOffer] = Field(default_factory=list)
    tunisia_sourcing_offers: list[TunisiaSourcingOffer] = Field(default_factory=list)
    tunisia_retail_market: TunisiaRetailMarket = Field(default_factory=TunisiaRetailMarket)
    tunisia_cheapest_suppliers: list[TunisiaBenchmarkSupplier] = Field(default_factory=list)
    china_cheapest_suppliers: list[ChinaBenchmarkSupplier] = Field(default_factory=list)
    research_sources: list[BenchmarkResearchSource] = Field(default_factory=list)
    raw_sources: list[ProviderRawSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        if not self.china_sourcing_offers and self.china_cheapest_suppliers:
            self.china_sourcing_offers = [
                ChinaSourcingOffer.model_validate(offer.model_dump())
                for offer in self.china_cheapest_suppliers
            ]
        if not self.china_cheapest_suppliers and self.china_sourcing_offers:
            self.china_cheapest_suppliers = [
                ChinaBenchmarkSupplier.model_validate(
                    _model_dump_with_supported_type(
                        offer,
                        {"manufacturer", "trading_company", "marketplace_source", "supplier_profile", "unknown"},
                    )
                )
                for offer in self.china_sourcing_offers
            ]
        if not self.tunisia_sourcing_offers and self.tunisia_cheapest_suppliers:
            self.tunisia_sourcing_offers = [
                TunisiaSourcingOffer.model_validate(
                    _model_dump_with_supported_type(
                        offer,
                        {"wholesaler", "importer", "distributor", "manufacturer", "b2b_seller", "marketplace_source", "unknown"},
                    )
                )
                for offer in self.tunisia_cheapest_suppliers
            ]
        if not self.tunisia_cheapest_suppliers and self.tunisia_sourcing_offers:
            self.tunisia_cheapest_suppliers = [
                TunisiaBenchmarkSupplier.model_validate(
                    _model_dump_with_supported_type(
                        offer,
                        {"marketplace", "local_provider", "seller", "source", "unknown"},
                    )
                )
                for offer in self.tunisia_sourcing_offers
            ]


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


def _model_dump_with_supported_type(model: StrictModel, supported_types: set[str]) -> dict:
    data = model.model_dump()
    if data.get("type") not in supported_types:
        data["type"] = "unknown"
    return data
