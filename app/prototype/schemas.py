from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas import ProductUnderstanding, StrictModel
from app.benchmark.schemas import ChinaSourcingOffer, TunisiaRetailMarket, TunisiaSourcingOffer


Recommendation = Literal["go", "no_go", "investigate_more"]
SellerDensity = Literal["low", "medium", "high", "unknown"]


class PrototypeAnalyzeRequest(StrictModel):
    product: str = Field(default="", max_length=300)
    quantity_scenarios: list[int] = Field(default_factory=lambda: [100, 1000])


class PrototypeSourcingLink(StrictModel):
    title: str = ""
    url: str
    price: str | None = None
    moq: str | None = None
    confidence: str = "low"


class ExampleRetailPrice(StrictModel):
    seller_name: str = ""
    product_title: str | None = None
    price_tnd: float | None = None
    price_range_tnd: str | None = None
    source_url: str | None = None
    confidence: str = "low"


class SourcingSummary(StrictModel):
    china_price_range: str = ""
    china_price_min_tnd_estimate: float | None = None
    china_price_max_tnd_estimate: float | None = None
    china_moq_summary: str = ""
    tunisia_wholesale_summary: str = ""
    tunisia_wholesale_found: bool = False
    evidence_confidence: str = "low"


class RetailMarketSummary(StrictModel):
    retail_price_range_tnd: str = ""
    retail_min_tnd: float | None = None
    retail_max_tnd: float | None = None
    retail_avg_tnd: float | None = None
    seller_density: SellerDensity = "unknown"
    example_retail_prices: list[ExampleRetailPrice] = Field(default_factory=list)
    competition_notes: str = ""
    availability_notes: str = ""


class ProfitabilityEstimate(StrictModel):
    estimated_source_cost_tnd: float | None = None
    estimated_selling_price_tnd: float | None = None
    estimated_meta_ads_cost_per_sale_tnd: float | None = None
    estimated_profit_per_unit_tnd: float | None = None
    estimated_profit_for_100_units_tnd: float | None = None
    estimated_profit_for_1000_units_tnd: float | None = None
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class HiddenSourcingLinks(StrictModel):
    china_sourcing_links: list[PrototypeSourcingLink] = Field(default_factory=list)
    tunisia_sourcing_links: list[PrototypeSourcingLink] = Field(default_factory=list)


class PrototypeAnalyzeResponse(StrictModel):
    run_id: str
    product_understanding: ProductUnderstanding | dict = Field(default_factory=dict)
    product_image_url: str | None = None
    product_description: str = ""
    sourcing_summary: SourcingSummary = Field(default_factory=SourcingSummary)
    retail_market_summary: RetailMarketSummary = Field(default_factory=RetailMarketSummary)
    profitability_estimate: ProfitabilityEstimate = Field(default_factory=ProfitabilityEstimate)
    recommendation: Recommendation = "investigate_more"
    recommendation_reason: str = ""
    go_reveal_available: bool = True
    warnings: list[str] = Field(default_factory=list)
    links_hidden: bool = True
    hidden_sourcing_links: HiddenSourcingLinks = Field(default_factory=HiddenSourcingLinks, exclude=True)


class PrototypeRevealResponse(StrictModel):
    run_id: str
    china_sourcing_links: list[PrototypeSourcingLink] = Field(default_factory=list)
    tunisia_sourcing_links: list[PrototypeSourcingLink] = Field(default_factory=list)
    sourcing_agents: list["SourcingAgent"] = Field(default_factory=list)


class CostConfig(StrictModel):
    firecrawl_cost_per_call: float = 0.0
    tavily_cost_per_call: float = 0.0
    exa_cost_per_call: float = 0.0
    gemini_intent_cost_per_call: float = 0.0
    gemini_analysis_cost_per_call: float = 0.0
    usd_to_tnd_rate: float = 3.1
    default_meta_ads_cost_per_sale_tnd: float = 5.0
    default_shipping_per_unit_tnd: float = 0.0
    default_customs_or_import_rate_percent: float = 0.0
    default_misc_cost_per_unit_tnd: float = 0.0


class SourcingAgent(StrictModel):
    id: int = 0
    name: str = ""
    company_name: str = ""
    country_or_region: str = ""
    email: str = ""
    phone: str = ""
    whatsapp: str = ""
    website: str = ""
    notes: str = ""
    active: bool = True


class AnalyticsRunSummary(StrictModel):
    run_id: str
    timestamp: str
    product_input: str
    normalized_product: str = ""
    provider_fallback_path: list[str] = Field(default_factory=list)
    firecrawl_called: bool = False
    tavily_called: bool = False
    exa_called: bool = False
    gemini_intent_calls: int = 0
    gemini_analysis_calls: int = 0
    provider_api_calls: int = 0
    raw_sources_collected: int = 0
    sources_used_in_final_analysis: int = 0
    latency_ms: int = 0
    status: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    estimated_research_cost_usd: float = 0.0


class AnalyticsRunDetail(AnalyticsRunSummary):
    provider_attempts: list[dict] = Field(default_factory=list)
    api_usage_events: list[dict] = Field(default_factory=list)


class AnalyticsSummary(StrictModel):
    total_runs: int = 0
    total_estimated_research_cost_usd: float = 0.0
    average_latency_ms: float = 0.0
    provider_call_counts: dict[str, int] = Field(default_factory=dict)


class PrototypeAnalysisDraft(StrictModel):
    product_description: str = ""
    product_image_url: str | None = None
    china_sourcing_offers: list[ChinaSourcingOffer] = Field(default_factory=list)
    tunisia_sourcing_offers: list[TunisiaSourcingOffer] = Field(default_factory=list)
    tunisia_retail_market: TunisiaRetailMarket = Field(default_factory=TunisiaRetailMarket)
    sourcing_summary: SourcingSummary = Field(default_factory=SourcingSummary)
    retail_market_summary: RetailMarketSummary = Field(default_factory=RetailMarketSummary)
    profitability_estimate: ProfitabilityEstimate = Field(default_factory=ProfitabilityEstimate)
    recommendation: Recommendation = "investigate_more"
    recommendation_reason: str = ""
    warnings: list[str] = Field(default_factory=list)


PrototypeRevealResponse.model_rebuild()
