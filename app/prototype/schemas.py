from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas import ProductUnderstanding, StrictModel
from app.benchmark.schemas import ChinaSourcingOffer, TunisiaRetailMarket, TunisiaSourcingOffer


Recommendation = Literal["go", "no_go", "investigate_more"]
SellerDensity = Literal["low", "medium", "high", "unknown"]
DecisionConfidence = Literal["low", "medium", "high"]
DominantDecisionSide = Literal["go", "no_go", "balanced"]


class PrototypeAnalyzeRequest(StrictModel):
    product: str = Field(default="", max_length=300)
    quantity_scenarios: list[int] = Field(default_factory=lambda: [1000])


class PrototypeSourcingLink(StrictModel):
    title: str = ""
    url: str
    price: str | None = None
    moq: str | None = None
    confidence: str = "low"
    evidence_sources: list[dict] = Field(default_factory=list)


class ContactSellerCard(StrictModel):
    seller_name: str = ""
    company_name: str = ""
    country: str = ""
    email: str | None = None
    email_source: str | None = None
    phone: str | None = None
    phone_source: str | None = None
    whatsapp: str | None = None
    whatsapp_source: str | None = None
    website: str | None = None
    website_source: str | None = None
    platform: str | None = None
    contact_page_url: str | None = None
    contact_page_source: str | None = None
    contact_confidence: Literal["high", "medium", "low"] = "low"
    contact_notes: str = ""


class ContactEnrichmentMetrics(StrictModel):
    contacts_found_count: int = 0
    contacts_with_email_count: int = 0
    contacts_with_whatsapp_count: int = 0
    contact_enrichment_latency: int = 0
    contact_enrichment_status: str = "not_found"
    contact_enrichment_reason: str = ""
    contact_cards_rejected_count: int = 0
    contact_rejection_reasons: list[str] = Field(default_factory=list)
    usable_contacts_found_count: int = 0


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
    source_unit_price_tnd: float | None = None
    estimated_shipping_per_unit_tnd: float | None = None
    estimated_customs_per_unit_tnd: float | None = None
    estimated_handling_per_unit_tnd: float | None = None
    estimated_misc_per_unit_tnd: float | None = None
    estimated_landed_cost_per_unit_tnd: float | None = None
    landed_cost_breakdown_notes: str = ""
    estimated_meta_campaign_budget_tnd: float | None = None
    expected_units_sold_from_campaign: float | None = None
    estimated_ad_cost_per_sold_unit_tnd: float | None = None
    ad_cost_notes: str = ""
    estimated_source_cost_tnd: float | None = None
    estimated_selling_price_tnd: float | None = None
    estimated_meta_ads_cost_per_sale_tnd: float | None = None
    gross_margin_per_unit_before_marketing_tnd: float | None = None
    gross_profit_for_1000_before_marketing_tnd: float | None = None
    net_profit_for_1000_after_marketing_tnd: float | None = None
    estimated_margin_per_unit_tnd: float | None = None
    estimated_profit_per_unit_tnd: float | None = None
    estimated_profit_for_100_units_tnd: float | None = None
    estimated_profit_for_1000_units_tnd: float | None = None
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class DecisionScores(StrictModel):
    go_percent: int = 0
    no_go_percent: int = 100
    confidence: DecisionConfidence = "low"
    go_reason: str = ""
    no_go_reason: str = ""
    score_explanation: str = ""
    why_go_score: list[str] = Field(default_factory=list)
    why_no_go_score: list[str] = Field(default_factory=list)
    dominant_side: DominantDecisionSide = "balanced"
    what_would_change_the_decision: list[str] = Field(default_factory=list)
    main_decision_factors: list[str] = Field(default_factory=list)


class HiddenSourcingLinks(StrictModel):
    china_sourcing_links: list[PrototypeSourcingLink] = Field(default_factory=list)
    tunisia_sourcing_links: list[PrototypeSourcingLink] = Field(default_factory=list)
    seller_contacts: list[ContactSellerCard] = Field(default_factory=list)
    retail_evidence_debug: dict = Field(default_factory=dict)
    product_image_debug: dict = Field(default_factory=dict)


class LocalizedClientAnalysis(StrictModel):
    product_description_en: str = ""
    product_description_fr: str = ""
    price_analysis_en: str = ""
    price_analysis_fr: str = ""
    market_analysis_en: str = ""
    market_analysis_fr: str = ""
    business_reading_en: str = ""
    business_reading_fr: str = ""


class PrototypeAnalyzeResponse(StrictModel):
    run_id: str
    product_understanding: ProductUnderstanding | dict = Field(default_factory=dict)
    product_image_url: str | None = None
    product_image_source_url: str | None = None
    product_image_confidence: Literal["high", "medium", "low", "fallback"] = "fallback"
    product_image_notes: str = "No reliable source-backed product image was found."
    product_description: str = ""
    localized_analysis: LocalizedClientAnalysis = Field(default_factory=LocalizedClientAnalysis)
    sourcing_summary: SourcingSummary = Field(default_factory=SourcingSummary)
    retail_market_summary: RetailMarketSummary = Field(default_factory=RetailMarketSummary)
    profitability_estimate: ProfitabilityEstimate = Field(default_factory=ProfitabilityEstimate)
    analysis_quantity_units: int = 1000
    decision_scores: DecisionScores = Field(default_factory=DecisionScores)
    decision_summary: str = ""
    positive_signals: list[str] = Field(default_factory=list)
    risk_signals: list[str] = Field(default_factory=list)
    main_decision_factors: list[str] = Field(default_factory=list)
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
    seller_contacts: list[ContactSellerCard] = Field(default_factory=list)
    sourcing_agents: list["SourcingAgent"] = Field(default_factory=list)


class CostConfig(StrictModel):
    firecrawl_cost_per_call: float = 0.0
    tavily_cost_per_call: float = 0.0
    exa_cost_per_call: float = 0.0
    gemini_intent_cost_per_call: float = 0.0
    gemini_analysis_cost_per_call: float = 0.0
    usd_to_tnd_rate: float = 3.1
    default_meta_ads_cost_per_sale_tnd: float = 5.0
    default_meta_campaign_budget_tnd: float | None = 300.0
    default_expected_units_sold_from_campaign: float | None = None
    default_shipping_per_unit_tnd: float = 4.0
    default_customs_or_import_rate_percent: float = 10.0
    default_handling_per_unit_tnd: float = 0.0
    default_misc_cost_per_unit_tnd: float = 2.0


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
    contact_enrichment_called: bool = False
    contact_provider_attempts: int = 0
    contact_search_api_calls: int = 0
    contacts_found_count: int = 0
    contacts_with_email_count: int = 0
    contacts_with_whatsapp_count: int = 0
    contact_enrichment_latency: int = 0
    contact_enrichment_estimated_cost: float = 0.0
    contact_enrichment_status: str = "not_found"
    contact_enrichment_reason: str = ""
    contact_cards_rejected_count: int = 0
    contact_rejection_reasons: list[str] = Field(default_factory=list)
    usable_contacts_found_count: int = 0
    was_product_image_found: bool = False
    product_image_source_url: str | None = None
    product_image_candidates_count: int = 0
    product_image_selected_source: str | None = None
    product_image_rejection_reasons: list[str] = Field(default_factory=list)
    source_unit_price_tnd: float | None = None
    estimated_landed_cost_per_unit_tnd: float | None = None
    landed_cost_breakdown_notes: str = ""
    estimated_meta_campaign_budget_tnd: float | None = None
    expected_units_sold_from_campaign: float | None = None
    estimated_ad_cost_per_sold_unit_tnd: float | None = None
    hidden_sourcing_urls_count: int = 0
    selected_sourcing_offers_count: int = 0
    retail_candidate_sources_before_cap: int = 0
    retail_candidate_sources_after_cap: int = 0
    dropped_retail_sources: int = 0
    known_tunisian_retail_domains_found: list[str] = Field(default_factory=list)


class AnalyticsRunDetail(AnalyticsRunSummary):
    provider_attempts: list[dict] = Field(default_factory=list)
    api_usage_events: list[dict] = Field(default_factory=list)
    hidden_links: dict = Field(default_factory=dict)
    seller_contacts: list[ContactSellerCard] = Field(default_factory=list)


class AnalyticsSummary(StrictModel):
    total_runs: int = 0
    total_estimated_research_cost_usd: float = 0.0
    average_latency_ms: float = 0.0
    provider_call_counts: dict[str, int] = Field(default_factory=dict)


class PrototypeAnalysisDraft(StrictModel):
    product_description: str = ""
    localized_analysis: LocalizedClientAnalysis = Field(default_factory=LocalizedClientAnalysis)
    product_image_url: str | None = None
    china_sourcing_offers: list[ChinaSourcingOffer] = Field(default_factory=list)
    tunisia_sourcing_offers: list[TunisiaSourcingOffer] = Field(default_factory=list)
    tunisia_retail_market: TunisiaRetailMarket = Field(default_factory=TunisiaRetailMarket)
    sourcing_summary: SourcingSummary = Field(default_factory=SourcingSummary)
    retail_market_summary: RetailMarketSummary = Field(default_factory=RetailMarketSummary)
    profitability_estimate: ProfitabilityEstimate = Field(default_factory=ProfitabilityEstimate)
    decision_scores: DecisionScores = Field(default_factory=DecisionScores)
    recommendation: Recommendation = "investigate_more"
    recommendation_reason: str = ""
    warnings: list[str] = Field(default_factory=list)


PrototypeRevealResponse.model_rebuild()
