from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from statistics import median
import time
from typing import Iterable
from urllib.parse import urlparse

from app.benchmark.providers.base import ProviderAdapterError, ProviderNotConfiguredError
from app.benchmark.schemas import (
    ChinaSourcingOffer,
    ProviderAnalysisResult,
    ProviderEvidence,
    ProviderRawSource,
    TunisiaSourcingOffer,
)
from app.benchmark.validation import validate_provider_result
from app.services.gemini_client import _extract_gemini_status_code
from app.prototype.schemas import (
    ComparabilityAssessment,
    CostConfig,
    DecisionScores,
    DetailedScoring,
    ExampleRetailPrice,
    HiddenSourcingLinks,
    LandedCostComponentView,
    LandedCostView,
    LocalizedClientAnalysis,
    ProfitabilityEstimate,
    PrototypeAnalyzeRequest,
    PrototypeAnalyzeResponse,
    PrototypeAnalysisDraft,
    PrototypeSourcingLink,
    RetailMarketSummary,
    RetailOfferView,
    SourcingOfferView,
    SourcingSummary,
    ScoreCriterion,
    SourceReference,
)
from app.prototype.storage import PrototypeStore
from app.schemas import IntentResult, ProductUnderstanding


EVIDENCE_GROUPS = ("china_sourcing", "tunisia_sourcing", "tunisia_retail")
TUNISIA_WHOLESALE_NOT_FOUND = "Aucun prix grossiste tunisien public fiable n’a été identifié pour ce produit."
ANALYSIS_QUANTITY_UNITS = 1000
DIGITAL_AD_BUDGET_MIN_TND = 300.0
DIGITAL_AD_BUDGET_MAX_TND = 500.0
DIGITAL_AD_BUDGET_DEFAULT_TND = 400.0
IMAGE_MARKDOWN_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)", re.IGNORECASE)
IMAGE_HTML_RE = re.compile(r"""<img[^>]+src=["'](https?://[^"']+)["']""", re.IGNORECASE)
META_IMAGE_RE = re.compile(r"""(?:og:image|twitter:image)[^"'=:\n\r>]*[:=]\s*["']?(https?://[^"'\s>]+)""", re.IGNORECASE)
IMAGE_URL_RE = re.compile(r"""https?://[^\s"'()<>]+\.(?:png|jpe?g|webp|gif|svg)(?:\?[^\s"'()<>]*)?""", re.IGNORECASE)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DecisionScoreContext:
    model_recommendation: str
    final_recommendation: str
    recommendation_reason: str
    gross_margin: float | None
    validated: ProviderAnalysisResult
    profitability: ProfitabilityEstimate | None
    product: ProductUnderstanding | None = None


class PrototypeResearchOrchestrator:
    def __init__(
        self,
        intent_client,
        analysis_client,
        providers: list[object],
        store: PrototypeStore,
        cost_config: CostConfig | None = None,
        contact_providers: list[object] | None = None,
    ) -> None:
        self.intent_client = intent_client
        self.analysis_client = analysis_client
        self.providers = providers
        self.store = store
        self.cost_config = cost_config or self.store.get_cost_config()

    async def analyze(self, request: PrototypeAnalyzeRequest) -> PrototypeAnalyzeResponse:
        started = time.perf_counter()
        product_input = request.product.strip()
        _log_analysis_stage("intent")
        intent_started = time.perf_counter()
        try:
            intent = await self.intent_client.classify(product_input)
        except Exception as error:
            _log_stage_failure("intent", error, intent_started)
            raise
        run_id = self.store.create_run(
            product_input=product_input,
            normalized_product=intent.normalized_product or "",
            status="running",
            latency_ms=0,
            warnings=list(intent.warnings),
            errors=[],
            product_understanding=_product_dump(intent),
        )
        self.store.log_api_usage(run_id, "gemini_intent", 1)

        if not intent.is_valid_product or not intent.normalized_product:
            response = PrototypeAnalyzeResponse(
                run_id=run_id,
                target_market=request.market,
                sourcing_country=request.sourcing_country,
                product_understanding=_product_dump(intent),
                product_description="",
                recommendation="no_go",
                recommendation_reason=intent.reason,
                warnings=list(intent.warnings),
            )
            self.store.update_run_payload(
                run_id,
                "invalid_product",
                _elapsed_ms(started),
                response.warnings,
                [],
                response.model_dump(exclude={"hidden_sourcing_links"}),
                response.hidden_sourcing_links.model_dump(),
            )
            return response

        product = intent.product_understanding or ProductUnderstanding(
            original_product=product_input,
            normalized_product=intent.normalized_product,
            english_search_name=intent.normalized_product,
            french_search_name=intent.normalized_product,
        )
        _log_analysis_stage("recherche")
        research_started = time.perf_counter()
        try:
            evidence, warnings = await self._collect_evidence(run_id, product)
        except Exception as error:
            _log_stage_failure("recherche", error, research_started)
            raise
        if _best_source_image(evidence, product) is None:
            image_evidence = await self._collect_image_evidence(run_id, product)
            if image_evidence.sources:
                evidence = evidence.model_copy(
                    update={
                        "sources": _dedupe_sources([*evidence.sources, *image_evidence.sources]),
                        "raw_queries_count": evidence.raw_queries_count + image_evidence.raw_queries_count,
                        "provider_api_calls": evidence.provider_api_calls + image_evidence.provider_api_calls,
                    }
                )
        try:
            _log_analysis_stage("extraction")
            extraction_started = time.perf_counter()
            analysis_result = await self._extract_analysis(product, evidence, request.quantity_scenarios)
            self.store.log_api_usage(run_id, "gemini_analysis", 1)
            logger.info(
                "ANALYSE_STAGE=extraction status=success duration_ms=%s",
                _elapsed_ms(extraction_started),
            )
        except Exception as error:
            _log_stage_failure("extraction", error, extraction_started)
            # Do not turn a technical extraction failure into an empty business
            # result. The HTTP layer normalizes this exception to a temporary
            # unavailability response; no score or decision is calculated.
            raise
        _log_analysis_stage("validation")
        validation_started = time.perf_counter()
        try:
            validated = validate_provider_result(_as_provider_analysis(analysis_result), evidence.sources)
        except Exception as error:
            _log_stage_failure("validation", error, validation_started)
            raise
        logger.info(
            "ANALYSE_STAGE=validation status=success duration_ms=%s",
            _elapsed_ms(validation_started),
        )
        _log_analysis_stage("calcul")
        calculation_started = time.perf_counter()
        try:
            response = _to_client_response(
                run_id=run_id,
                product=product,
                draft=analysis_result,
                validated=validated,
                evidence=evidence,
                cost_config=self.cost_config,
                quantity_scenarios=request.quantity_scenarios,
                warnings=list(dict.fromkeys(intent.warnings + warnings + validated.warnings)),
                target_market=request.market,
                sourcing_country=request.sourcing_country,
            )
        except Exception as error:
            _log_stage_failure("calcul", error, calculation_started)
            raise
        logger.info(
            "ANALYSE_STAGE=calcul status=success duration_ms=%s",
            _elapsed_ms(calculation_started),
        )
        self.store.update_run_payload(
            run_id,
            "success",
            _elapsed_ms(started),
            response.warnings,
            [],
            response.model_dump(exclude={"hidden_sourcing_links"}),
            response.hidden_sourcing_links.model_dump(),
        )
        return response

    async def reveal(self, run_id: str):
        return self.store.get_reveal(run_id)

    async def _collect_evidence(
        self,
        run_id: str,
        product: ProductUnderstanding,
    ) -> tuple[ProviderEvidence, list[str]]:
        collected: list[ProviderRawSource] = []
        warnings: list[str] = []
        sufficient = {group: False for group in EVIDENCE_GROUPS}
        provider_ids: list[str] = []

        for provider in self.providers:
            provider_id = getattr(provider, "provider_id", "unknown")
            provider_ids.append(provider_id)
            for group in EVIDENCE_GROUPS:
                if sufficient[group]:
                    continue
                group_started = time.perf_counter()
                try:
                    evidence = await provider.search_group(product, group)
                    collected.extend(evidence.sources)
                    self.store.log_provider_attempt(
                        run_id,
                        provider_id,
                        group,
                        "success",
                        evidence.provider_api_calls,
                        len(evidence.sources),
                        _elapsed_ms(group_started),
                    )
                    sufficient[group] = _is_group_sufficient(group, _sources_for_group(collected, group))
                except (ProviderNotConfiguredError, ProviderAdapterError) as error:
                    self.store.log_provider_attempt(
                        run_id,
                        provider_id,
                        group,
                        "failed",
                        0,
                        0,
                        _elapsed_ms(group_started),
                    )
                    warnings.append(f"{provider_id} could not provide {group} evidence.")
                    continue
            if all(sufficient.values()):
                break

        if not sufficient["tunisia_sourcing"]:
            warnings.append(TUNISIA_WHOLESALE_NOT_FOUND)
        return (
            ProviderEvidence(
                provider_id="prototype_fallback",
                sources=_dedupe_sources(collected),
                raw_queries_count=sum(1 for _ in provider_ids),
                provider_api_calls=0,
                warnings=warnings,
            ),
            warnings,
        )

    async def _collect_image_evidence(
        self,
        run_id: str,
        product: ProductUnderstanding,
    ) -> ProviderEvidence:
        collected: list[ProviderRawSource] = []
        raw_queries = 0
        api_calls = 0
        for provider in self.providers:
            dedicated = await self._search_image_group(run_id, provider, product, "image_discovery")
            collected.extend(dedicated.sources)
            raw_queries += dedicated.raw_queries_count
            api_calls += dedicated.provider_api_calls
            if _best_source_image(dedicated, product):
                break
            fallback = await self._search_image_group(run_id, provider, product, "tunisia_retail")
            collected.extend(fallback.sources)
            raw_queries += fallback.raw_queries_count
            api_calls += fallback.provider_api_calls
            if _best_source_image(fallback, product):
                break
        return ProviderEvidence(
            provider_id="prototype_image_discovery",
            sources=_dedupe_sources(collected),
            raw_queries_count=raw_queries,
            provider_api_calls=api_calls,
        )

    async def _search_image_group(
        self,
        run_id: int,
        provider: object,
        product: ProductUnderstanding,
        group: str,
    ) -> ProviderEvidence:
        provider_id = getattr(provider, "provider_id", "unknown")
        started = time.perf_counter()
        try:
            evidence = await provider.search_group(product, group)
        except (ProviderNotConfiguredError, ProviderAdapterError):
            self.store.log_provider_attempt(run_id, provider_id, group, "failed", 0, 0, _elapsed_ms(started))
            return ProviderEvidence(provider_id=provider_id)
        self.store.log_provider_attempt(
            run_id,
            provider_id,
            group,
            "success",
            evidence.provider_api_calls,
            len(evidence.sources),
            _elapsed_ms(started),
        )
        return evidence

    async def _extract_analysis(
        self,
        product: ProductUnderstanding,
        evidence: ProviderEvidence,
        quantity_scenarios: list[int],
    ):
        if hasattr(self.analysis_client, "extract_client_analysis"):
            return await self.analysis_client.extract_client_analysis(
                product,
                evidence,
                self.cost_config,
                quantity_scenarios,
            )
        return await self.analysis_client.extract(product, evidence)


def _is_group_sufficient(group: str, sources: list[ProviderRawSource]) -> bool:
    if group == "china_sourcing":
        return any(_has_price(source) and _has_china_sourcing_signal(source) for source in sources)
    if group == "tunisia_sourcing":
        return any(_has_price(source) and _has_tunisia_sourcing_signal(source) and not _looks_retail_or_foreign(source) for source in sources)
    if group == "tunisia_retail":
        retail_sources = [
            source for source in sources
            if _has_price(source) and _has_tunisia_retail_signal(source)
        ]
        return len({source.url for source in retail_sources}) >= 2
    return False


def _log_analysis_stage(stage: str) -> None:
    logger.info("ANALYSE_STAGE=%s", stage)


def _log_stage_failure(stage: str, error: Exception, started: float) -> None:
    logger.warning(
        "ANALYSE_STAGE=%s exception_type=%s provider_http_code=%s duration_ms=%s",
        stage,
        error.__class__.__name__,
        _extract_gemini_status_code(error),
        _elapsed_ms(started),
    )


def _has_price(source: ProviderRawSource) -> bool:
    text = _source_text(source)
    return any(marker in text for marker in ("$", "usd", "us$", "tnd", "dt", "د.ت")) or any(char.isdigit() for char in text)


def _has_china_sourcing_signal(source: ProviderRawSource) -> bool:
    text = _source_text(source)
    return any(signal in text for signal in ("moq", "factory", "manufacturer", "wholesale", "bulk", "oem", "odm", "china", "alibaba"))


def _has_tunisia_sourcing_signal(source: ProviderRawSource) -> bool:
    text = _source_text(source)
    return any(signal in text for signal in ("grossiste", "prix gros", "vente en gros", "fournisseur", "distributeur", "importateur", "fabricant", "usine", "b2b", "revendeur", "semi gros"))


def _has_tunisia_retail_signal(source: ProviderRawSource) -> bool:
    text = _source_text(source)
    return source.region_hint == "tunisia_retail" or any(signal in text for signal in ("boutique", "achat", "vente", "livraison", "magasin", "tayara", "mytek", "wamia", "tunisianet", "spacenet", "wikishop", "shopiwell", "keyshop", "affariyet"))


def _looks_retail_or_foreign(source: ProviderRawSource) -> bool:
    text = _source_text(source)
    url = source.url.lower()
    return any(marker in url for marker in (".dz", ".ma", ".fr")) or any(
        signal in text
        for signal in ("algerie", "algérie", "algeria", "maroc", "morocco", "france", "boutique", "panier", "mytek", "tayara")
    )


def _source_text(source: ProviderRawSource) -> str:
    return " ".join([source.title, source.snippet, source.content or ""]).lower()


def _sources_for_group(sources: Iterable[ProviderRawSource], group: str) -> list[ProviderRawSource]:
    return [source for source in sources if source.region_hint == group]


def _dedupe_sources(sources: list[ProviderRawSource]) -> list[ProviderRawSource]:
    by_url: dict[str, ProviderRawSource] = {}
    for source in sources:
        if source.url and source.url not in by_url:
            by_url[source.url] = source
    return list(by_url.values())


def _as_provider_analysis(analysis) -> ProviderAnalysisResult:
    if isinstance(analysis, ProviderAnalysisResult):
        return analysis
    if isinstance(analysis, PrototypeAnalysisDraft):
        return ProviderAnalysisResult(
            market_summary=analysis.product_description,
            china_sourcing_offers=analysis.china_sourcing_offers,
            tunisia_sourcing_offers=analysis.tunisia_sourcing_offers,
            tunisia_retail_market=analysis.tunisia_retail_market,
            warnings=analysis.warnings,
        )
    return ProviderAnalysisResult.model_validate(analysis)


def _to_client_response(
    run_id: str,
    product: ProductUnderstanding,
    draft,
    validated: ProviderAnalysisResult,
    evidence: ProviderEvidence,
    cost_config: CostConfig,
    quantity_scenarios: list[int],
    warnings: list[str],
    target_market: str = "Tunisia",
    sourcing_country: str = "China",
) -> PrototypeAnalyzeResponse:
    if isinstance(draft, PrototypeAnalysisDraft):
        computed = _response_from_validated(run_id, product, validated, evidence, cost_config, quantity_scenarios, warnings)
        draft_retail = _retail_summary_with_fallbacks(_retail_summary_from_validated(validated, product))
        base = computed.model_copy(
            update={
                **_image_payload(_valid_image_or_none(draft.product_image_url, evidence, product), evidence, product),
                "product_description": draft.product_description or computed.product_description,
                "localized_analysis": _localized_analysis_with_fallbacks(
                    draft.localized_analysis,
                    product,
                    draft.product_description or computed.product_description,
                    computed.sourcing_summary,
                    (
                        draft_retail
                        if validated.tunisia_retail_market.retail_offers
                        else _retail_summary_with_fallbacks(draft.retail_market_summary)
                    ),
                    computed.profitability_estimate,
                    validated,
                    computed.recommendation,
                    computed.recommendation_reason,
                ),
                "retail_market_summary": (
                    draft_retail
                    if validated.tunisia_retail_market.retail_offers
                    else _retail_summary_with_fallbacks(draft.retail_market_summary)
                ),
                "recommendation": computed.recommendation,
                "recommendation_reason": computed.recommendation_reason,
                "warnings": list(dict.fromkeys(warnings + draft.warnings)),
                "links_hidden": True,
            }
        )
    else:
        base = _response_from_validated(run_id, product, validated, evidence, cost_config, quantity_scenarios, warnings)

    hidden_links = HiddenSourcingLinks(
        china_sourcing_links=[
            _china_link(offer, cost_config, evidence)
            for offer in validated.china_sourcing_offers
            if offer.source_url
        ],
        tunisia_sourcing_links=[
            _tunisia_link(offer)
            for offer in validated.tunisia_sourcing_offers
            if offer.source_url
        ],
        retail_evidence_debug=_retail_evidence_debug(evidence, validated),
        product_image_debug=_product_image_debug(evidence, base),
    )
    sourcing_summary = base.sourcing_summary
    if not validated.tunisia_sourcing_offers:
        sourcing_summary = sourcing_summary.model_copy(
            update={
                "tunisia_wholesale_found": False,
                "tunisia_wholesale_summary": TUNISIA_WHOLESALE_NOT_FOUND,
            }
        )
    profitability = _profitability_with_evidence_risks(base.profitability_estimate, validated)
    profitability = _reconcile_profitability_supplier_price(profitability, validated, cost_config, product)
    profitability = _reconcile_profitability_market_price(profitability, validated, cost_config, product)
    recommendation, recommendation_reason = _conservative_recommendation(
        "investigate_more",
        profitability.gross_margin_min_tnd if profitability.gross_margin_min_tnd is not None else profitability.gross_margin_per_unit_before_marketing_tnd,
        validated,
        profitability,
        product,
    )
    decision_scores = _decision_scores(
        DecisionScoreContext(
            model_recommendation="investigate_more",
            final_recommendation=recommendation,
            recommendation_reason=recommendation_reason,
            gross_margin=profitability.gross_margin_min_tnd if profitability.gross_margin_min_tnd is not None else profitability.gross_margin_per_unit_before_marketing_tnd,
            validated=validated,
            profitability=profitability,
            product=product,
        )
    )
    decision_fields = _client_decision_fields(
        DecisionScoreContext(
            model_recommendation="investigate_more",
            final_recommendation=recommendation,
            recommendation_reason=recommendation_reason,
            gross_margin=profitability.gross_margin_min_tnd if profitability.gross_margin_min_tnd is not None else profitability.gross_margin_per_unit_before_marketing_tnd,
            validated=validated,
            profitability=profitability,
            product=product,
        ),
        decision_scores,
    )
    return base.model_copy(
        update={
            "target_market": target_market,
            "sourcing_country": sourcing_country,
            **_enrichment_fields(validated, evidence, cost_config, profitability, product),
            "sourcing_summary": sourcing_summary,
            "profitability_estimate": profitability,
            "decision_scores": decision_scores,
            **decision_fields,
            "recommendation": recommendation,
            "recommendation_reason": recommendation_reason,
            "hidden_sourcing_links": hidden_links,
            "links_hidden": True,
            "go_reveal_available": True,
        }
    )


def _response_from_validated(
    run_id: str,
    product: ProductUnderstanding,
    validated: ProviderAnalysisResult,
    evidence: ProviderEvidence,
    cost_config: CostConfig,
    quantity_scenarios: list[int],
    warnings: list[str],
) -> PrototypeAnalyzeResponse:
    comparable_china_offers = [
        offer for offer in validated.china_sourcing_offers
        if _supplier_target_package_price(offer, cost_config, product)[0] is not None
    ]
    china_prices = _china_price_points(comparable_china_offers)
    china_tnd = [round(price * cost_config.usd_to_tnd_rate, 2) for price in china_prices]
    source_min, source_max, source_offer = _canonical_supplier_price_range(validated, cost_config, product)
    # Keep the legacy scalar as the lower observed source bound; the complete
    # interval below is authoritative for client-facing profitability.
    source_unit_price = source_min if source_min is not None else source_max
    retail_target_prices = _retail_target_package_prices(validated.tunisia_retail_market.retail_offers, product)
    selling_min = min(retail_target_prices) if retail_target_prices else None
    selling_max = max(retail_target_prices) if retail_target_prices else None
    selling_price = round(median(retail_target_prices), 2) if retail_target_prices else None
    pricing_basis = (
        "Prix fournisseur et prix de détail comparables normalisés au conditionnement cible."
        if source_min is not None and selling_price is not None
        else "Référence de prix comparable insuffisante pour calculer une rentabilité fiable."
    )
    landed_min, landed_max, landed_notes, landed_parts = _landed_cost_breakdown_range(source_min, source_max, cost_config)
    source_offer = _canonical_supplier_offer(validated, product)
    ad_allocation, ad_notes = _ad_allocation(cost_config)
    landed_cost = landed_min
    gross_margin_min = round(selling_min - landed_max, 2) if selling_min is not None and landed_max is not None else None
    gross_margin_max = round(selling_max - landed_min, 2) if selling_max is not None and landed_min is not None else None
    gross_margin = round(selling_price - landed_cost, 2) if selling_price is not None and landed_cost is not None else None
    gross_profit_1000 = (
        round(gross_margin * ANALYSIS_QUANTITY_UNITS, 2)
        if gross_margin is not None
        else None
    )
    campaign_budget = _digital_ad_budget_default(cost_config)
    net_profit_1000 = (
        round(gross_profit_1000 - float(campaign_budget), 2)
        if gross_profit_1000 is not None and campaign_budget is not None
        else None
    )
    net_profit_min = (
        round(gross_profit_1000 - _digital_ad_budget_max(cost_config), 2)
        if gross_profit_1000 is not None
        else None
    )
    net_profit_max = (
        round(gross_profit_1000 - _digital_ad_budget_min(cost_config), 2)
        if gross_profit_1000 is not None
        else None
    )
    recommendation, recommendation_reason = _conservative_recommendation("investigate_more", gross_margin_min, validated, None, product)
    decision_context = DecisionScoreContext(
        model_recommendation="investigate_more",
        final_recommendation=recommendation,
        recommendation_reason=recommendation_reason,
        gross_margin=gross_margin,
        validated=validated,
        profitability=None,
        product=product,
    )
    decision_scores = _decision_scores(decision_context)
    sourcing_summary = SourcingSummary(
        china_price_range=_range_text("TND", china_tnd),
        china_price_min_tnd_estimate=min(china_tnd) if china_tnd else None,
        china_price_max_tnd_estimate=max(china_tnd) if china_tnd else None,
        china_moq_summary=", ".join([offer.moq for offer in validated.china_sourcing_offers if offer.moq]) or "MOQ not found.",
        tunisia_wholesale_summary=_tunisia_wholesale_summary(validated.tunisia_sourcing_offers),
        tunisia_wholesale_found=bool(validated.tunisia_sourcing_offers),
        evidence_confidence=_overall_confidence(validated, product),
    )
    retail_summary = _retail_summary_from_validated(validated, product)
    profitability_estimate = ProfitabilityEstimate(
        source_unit_price_tnd=source_unit_price,
        source_unit_price_min_tnd=source_min,
        source_unit_price_max_tnd=source_max,
        source_price_unit=source_offer.price_unit if source_offer else None,
        source_price_unit_confirmed=bool(source_offer and source_offer.price_unit),
        estimated_shipping_per_unit_tnd=landed_parts["shipping"],
        estimated_customs_per_unit_tnd=landed_parts["customs"],
        estimated_handling_per_unit_tnd=landed_parts["handling"],
        estimated_misc_per_unit_tnd=landed_parts["misc"],
        estimated_landed_cost_per_unit_tnd=landed_cost,
        estimated_landed_cost_min_tnd=landed_min,
        estimated_landed_cost_max_tnd=landed_max,
        landed_cost_breakdown_notes=landed_notes,
        estimated_meta_campaign_budget_tnd=campaign_budget,
        digital_ad_budget_min_tnd=_digital_ad_budget_min(cost_config),
        digital_ad_budget_max_tnd=_digital_ad_budget_max(cost_config),
        digital_ad_budget_default_tnd=campaign_budget,
        expected_units_sold_from_campaign=cost_config.default_expected_units_sold_from_campaign,
        estimated_ad_cost_per_sold_unit_tnd=ad_allocation,
        ad_cost_notes=ad_notes,
        estimated_source_cost_tnd=landed_cost,
        estimated_selling_price_tnd=selling_price,
        estimated_selling_price_min_tnd=selling_min,
        estimated_selling_price_max_tnd=selling_max,
        pricing_basis=pricing_basis,
        estimated_meta_ads_cost_per_sale_tnd=ad_allocation,
        gross_margin_per_unit_before_marketing_tnd=gross_margin,
        gross_margin_min_tnd=gross_margin_min,
        gross_margin_max_tnd=gross_margin_max,
        gross_margin_percent_min=(round(gross_margin_min / selling_min * 100, 1) if gross_margin_min is not None and selling_min else None),
        gross_margin_percent_max=(round(gross_margin_max / selling_max * 100, 1) if gross_margin_max is not None and selling_max else None),
        gross_profit_for_1000_before_marketing_tnd=gross_profit_1000,
        net_profit_for_1000_after_marketing_tnd=net_profit_1000,
        net_profit_for_1000_after_advertising_min_tnd=net_profit_min,
        net_profit_for_1000_after_advertising_max_tnd=net_profit_max,
        estimated_margin_per_unit_tnd=gross_margin,
        estimated_profit_per_unit_tnd=gross_margin,
        estimated_profit_for_100_units_tnd=None,
        estimated_profit_for_1000_units_tnd=net_profit_1000,
        assumptions=[
            "Profitability is an estimate, not a guarantee.",
            f"Analysis quantity scenario: {ANALYSIS_QUANTITY_UNITS} units.",
            f"USD to TND rate assumed at {cost_config.usd_to_tnd_rate}.",
            pricing_basis,
            landed_notes,
            ad_notes,
        ],
        risks=list(dict.fromkeys(warnings + _evidence_risks(validated))),
    )
    localized_analysis = _localized_analysis_with_fallbacks(
        None,
        product,
        validated.market_summary or product.normalized_product,
        sourcing_summary,
        retail_summary,
        profitability_estimate,
        validated,
        recommendation,
        recommendation_reason,
    )

    return PrototypeAnalyzeResponse(
        run_id=run_id,
        product_understanding=product,
        **_image_payload(_first_source_image(evidence), evidence, product),
        product_description=validated.market_summary or product.normalized_product,
        localized_analysis=localized_analysis,
        sourcing_summary=sourcing_summary,
        retail_market_summary=retail_summary,
        analysis_quantity_units=ANALYSIS_QUANTITY_UNITS,
        profitability_estimate=profitability_estimate,
        recommendation=recommendation,
        recommendation_reason=recommendation_reason,
        decision_scores=decision_scores,
        **_client_decision_fields(decision_context, decision_scores),
        warnings=warnings,
    )


def _china_price_points(offers: list[ChinaSourcingOffer]) -> list[float]:
    return [
        price
        for offer in offers
        for price in (offer.price_min_usd_numeric, offer.price_max_usd_numeric)
        if price is not None
    ]


def _comparable_prices(
    validated: ProviderAnalysisResult,
    cost_config: CostConfig,
    product: ProductUnderstanding | None = None,
) -> tuple[float | None, float | None, str]:
    if product is not None:
        normalized_source = _canonical_supplier_price(validated, cost_config, product)
        target_volume, target_unit = _product_target_volume(product)
        retail_points = _retail_price_points(validated.tunisia_retail_market.retail_offers)
        comparable_retail = _target_package_retail_price(retail_points, target_volume, target_unit)
        if validated.china_sourcing_offers and target_volume and target_unit:
            return normalized_source, comparable_retail, "Supplier price normalized to the target package; Tunisia prices normalized to the same package."
    source_points = _source_price_points(
        validated.china_sourcing_offers,
        validated.tunisia_sourcing_offers,
        cost_config,
    )
    retail_points = _retail_price_points(validated.tunisia_retail_market.retail_offers)
    if not source_points or not retail_points:
        return _fallback_price_pair(source_points, retail_points)

    source_price, source_unit, source_volume = min(source_points, key=lambda point: point[0])
    retail_price, retail_unit = _average_price_for_unit(retail_points, source_unit)
    if retail_price is None:
        return _fallback_price_pair(source_points, retail_points)

    if source_unit and retail_unit and _volumes_differ(source_points, retail_points):
        source_base_volume = source_volume or 1.0
        retail_base_volume = _average_volume(retail_points, retail_unit)
        return (
            round(source_price / source_base_volume, 2),
            round(retail_price / retail_base_volume, 2),
            f"Prices normalized in TND/{source_unit} because package volumes differ.",
        )
    return source_price, round(retail_price, 2), "Comparable listed-package prices used; no volume conversion was required."


def _target_package_retail_price(
    retail_points: list[tuple[float, str | None, float | None]],
    target_volume: float | None,
    target_unit: str | None,
) -> float | None:
    if not target_volume or not target_unit:
        return None
    matching = [point for point in retail_points if point[1] == target_unit and point[2]]
    if not matching:
        return None
    comparable_prices = [price / volume * target_volume for price, _, volume in matching]
    return round(median(comparable_prices), 2)


def _retail_target_package_prices(offers: list, product: ProductUnderstanding | None) -> list[float]:
    if product is None:
        return []
    prices: list[float] = []
    for offer in offers:
        prices.extend(_retail_target_package_price_range(offer, product))
    return prices


def _retail_target_package_price_range(offer, product: ProductUnderstanding | None) -> list[float]:
    minimum = _retail_target_package_price(offer, product)
    if minimum is None:
        return []
    values = [minimum]
    raw = str(offer.price_range_tnd or "").replace(",", ".")
    numbers = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", raw)]
    if len(numbers) >= 2 and offer.price_min_tnd_numeric:
        maximum = offer.price_max_tnd_numeric or max(numbers[:2])
        if maximum != offer.price_min_tnd_numeric:
            target_min = offer.price_min_tnd_numeric
            target_max = maximum
            quantity, unit = _parse_volume(offer.product_title or "")
            target_volume, target_unit = _product_target_volume(product) if product else (None, None)
            offer_volume = _base_volume(quantity, unit)
            if target_volume and target_unit and offer_volume and _base_unit(unit) == target_unit:
                values.append(round(target_max / offer_volume * target_volume, 2))
            else:
                values.append(round(target_max, 2))
    return values


def _source_price_points(
    china_offers: list[ChinaSourcingOffer],
    tunisia_offers: list[TunisiaSourcingOffer],
    cost_config: CostConfig,
) -> list[tuple[float, str | None, float | None]]:
    china_points = []
    for offer in china_offers:
        price = offer.price_min_usd_numeric or offer.price_max_usd_numeric
        if price is None:
            continue
        volume, unit = _parse_volume(offer.product_title or offer.name)
        china_points.append((round(price * cost_config.usd_to_tnd_rate, 2), _base_unit(unit), _base_volume(volume, unit)))
    if china_points:
        return china_points
    return [
        (
            offer.price_min_tnd_numeric,
            _base_unit(_parse_volume(offer.product_title or offer.name)[1]),
            _base_volume(*_parse_volume(offer.product_title or offer.name)),
        )
        for offer in tunisia_offers
        if offer.price_min_tnd_numeric is not None
    ]


def _retail_price_points(offers: list) -> list[tuple[float, str | None, float | None]]:
    points = []
    for offer in offers:
        if offer.price_min_tnd_numeric is None:
            continue
        volume, unit = _parse_volume(offer.product_title or "")
        points.append((offer.price_min_tnd_numeric, _base_unit(unit), _base_volume(volume, unit)))
    return points


def _fallback_price_pair(source_points, retail_points) -> tuple[float | None, float | None, str]:
    source = min((point[0] for point in source_points), default=None)
    retail = sum(point[0] for point in retail_points) / len(retail_points) if retail_points else None
    return source, round(retail, 2) if retail is not None else None, "Listed prices used; volume comparability could not be fully verified."


def _average_price_for_unit(points, unit):
    matching = [point for point in points if point[1] == unit]
    if not matching:
        return None, None
    return sum(point[0] for point in matching) / len(matching), unit


def _average_volume(points, unit: str) -> float:
    volumes = [point[2] for point in points if point[1] == unit and point[2]]
    return sum(volumes) / len(volumes) if volumes else 1.0


def _volumes_differ(source_points, retail_points) -> bool:
    source_volume = next((point[2] for point in source_points if point[2]), None)
    retail_volume = next((point[2] for point in retail_points if point[2]), None)
    return source_volume is not None and retail_volume is not None and source_volume != retail_volume


def _base_unit(unit: str) -> str | None:
    if unit in {"L", "ml"}:
        return "L"
    if unit in {"kg", "g"}:
        return "kg"
    if unit == "pcs":
        return "pcs"
    return None


def _base_volume(quantity: float | None, unit: str) -> float | None:
    if quantity is None:
        return None
    if unit == "ml" or unit == "g":
        return quantity / 1000
    return quantity


def _localized_analysis_with_fallbacks(
    localized: LocalizedClientAnalysis | None,
    product: ProductUnderstanding,
    product_description: str,
    sourcing_summary: SourcingSummary,
    retail_summary: RetailMarketSummary,
    profitability: ProfitabilityEstimate,
    validated: ProviderAnalysisResult,
    recommendation: str,
    recommendation_reason: str,
) -> LocalizedClientAnalysis:
    base = localized or LocalizedClientAnalysis()
    fallback = _fallback_localized_analysis(
        product,
        product_description,
        sourcing_summary,
        retail_summary,
        profitability,
        validated,
        recommendation,
        recommendation_reason,
    )
    return base.model_copy(
        update={
            "product_description_en": base.product_description_en or fallback.product_description_en,
            "product_description_fr": base.product_description_fr or fallback.product_description_fr,
            "price_analysis_en": base.price_analysis_en or fallback.price_analysis_en,
            "price_analysis_fr": base.price_analysis_fr or fallback.price_analysis_fr,
            "market_analysis_en": base.market_analysis_en or fallback.market_analysis_en,
            "market_analysis_fr": base.market_analysis_fr or fallback.market_analysis_fr,
            "business_reading_en": base.business_reading_en or fallback.business_reading_en,
            "business_reading_fr": base.business_reading_fr or fallback.business_reading_fr,
        }
    )


def _fallback_localized_analysis(
    product: ProductUnderstanding,
    product_description: str,
    sourcing_summary: SourcingSummary,
    retail_summary: RetailMarketSummary,
    profitability: ProfitabilityEstimate,
    validated: ProviderAnalysisResult,
    recommendation: str,
    recommendation_reason: str,
) -> LocalizedClientAnalysis:
    product_name = product.normalized_product or product.original_product or "this product"
    seller_count = len(retail_summary.example_retail_prices) or len(validated.tunisia_retail_market.retail_offers)
    product_description_en = (
        f"{product_description or product_name} This run focuses on {product_name} using "
        f"{len(validated.china_sourcing_offers)} China sourcing offer(s), "
        f"{len(validated.tunisia_sourcing_offers)} Tunisia wholesale offer(s), and "
        f"{seller_count} Tunisia retail reference(s)."
    ).strip()
    product_description_fr = (
        f"{product_description or product_name} Cette analyse porte sur {product_name} avec "
        f"{len(validated.china_sourcing_offers)} offre(s) sourcing Chine, "
        f"{len(validated.tunisia_sourcing_offers)} offre(s) grossiste Tunisie et "
        f"{seller_count} référence(s) de prix de détail en Tunisie."
    ).strip()
    return LocalizedClientAnalysis(
        product_description_en=product_description_fr,
        product_description_fr=product_description_fr,
        price_analysis_en=_fallback_price_analysis_fr(product_name, sourcing_summary, retail_summary, profitability),
        price_analysis_fr=_fallback_price_analysis_fr(product_name, sourcing_summary, retail_summary, profitability),
        market_analysis_en=_fallback_market_analysis_fr(product_name, retail_summary, validated),
        market_analysis_fr=_fallback_market_analysis_fr(product_name, retail_summary, validated),
        business_reading_en=_fallback_business_reading_fr(product_name, profitability, recommendation, recommendation_reason),
        business_reading_fr=_fallback_business_reading_fr(product_name, profitability, recommendation, recommendation_reason),
    )


def _fallback_price_analysis_en(
    product_name: str,
    sourcing_summary: SourcingSummary,
    retail_summary: RetailMarketSummary,
    profitability: ProfitabilityEstimate,
) -> str:
    china_text = (
        f"China sourcing for {product_name} shows {sourcing_summary.china_price_range}"
        if sourcing_summary.china_price_range
        else f"No source-backed China unit price was confirmed for {product_name}"
    )
    tunisia_text = (
        sourcing_summary.tunisia_wholesale_summary
        if sourcing_summary.tunisia_wholesale_summary
        else "No Tunisia wholesale offer with usable price evidence was confirmed"
    )
    retail_text = (
        f"Tunisia retail references sit around {retail_summary.retail_price_range_tnd}"
        if retail_summary.retail_price_range_tnd
        else "Tunisia retail pricing is still not visible enough"
    )
    landed_text = (
        f"Estimated landed cost is {profitability.estimated_landed_cost_per_unit_tnd:g} TND/unit before advertising."
        if profitability.estimated_landed_cost_per_unit_tnd is not None
        else profitability.landed_cost_breakdown_notes or "Landed cost could not be estimated yet."
    )
    return f"{china_text}. {tunisia_text}. {retail_text}. {landed_text}"


def _fallback_price_analysis_fr(
    product_name: str,
    sourcing_summary: SourcingSummary,
    retail_summary: RetailMarketSummary,
    profitability: ProfitabilityEstimate,
) -> str:
    china_text = (
        f"Le sourcing Chine pour {product_name} montre {sourcing_summary.china_price_range}"
        if sourcing_summary.china_price_range
        else f"Aucun prix unitaire Chine fiable n'a été confirmé pour {product_name}"
    )
    tunisia_text = (
        sourcing_summary.tunisia_wholesale_summary
        if sourcing_summary.tunisia_wholesale_summary
        else "Aucune offre grossiste tunisienne avec prix exploitable n'a été confirmée"
    )
    retail_text = (
        f"Les références de prix de détail en Tunisie se situent autour de {retail_summary.retail_price_range_tnd}"
        if retail_summary.retail_price_range_tnd
        else "Les prix retail en Tunisie restent trop peu visibles"
    )
    landed_text = (
        f"Le coût rendu estimé est de {_format_number(profitability.estimated_landed_cost_per_unit_tnd)} TND/unité."
        if profitability.estimated_landed_cost_per_unit_tnd is not None
        else profitability.landed_cost_breakdown_notes or "Le coût rendu ne peut pas encore être estimé."
    )
    return f"{china_text}. {tunisia_text}. {retail_text}. {landed_text}"


def _fallback_market_analysis_en(
    product_name: str,
    retail_summary: RetailMarketSummary,
    validated: ProviderAnalysisResult,
) -> str:
    seller_count = len(retail_summary.example_retail_prices) or len(validated.tunisia_retail_market.retail_offers)
    density = retail_summary.seller_density
    competition = retail_summary.competition_notes or "No extra competition notes were extracted."
    availability = retail_summary.availability_notes or "Availability signals remain limited to the captured listings."
    if seller_count:
        return (
            f"For {product_name}, the Tunisia retail view currently includes {seller_count} seller reference(s), "
            f"which suggests {density} visible seller density. {competition} {availability}"
        )
    return (
        f"For {product_name}, Tunisia market validation is still thin because no priced retail seller references were confirmed. "
        f"{competition} {availability}"
    )


def _fallback_market_analysis_fr(
    product_name: str,
    retail_summary: RetailMarketSummary,
    validated: ProviderAnalysisResult,
) -> str:
    seller_count = len(retail_summary.example_retail_prices) or len(validated.tunisia_retail_market.retail_offers)
    density = retail_summary.seller_density
    competition = retail_summary.competition_notes or "Aucune note concurrentielle supplémentaire n'a été extraite."
    availability = retail_summary.availability_notes or "Les signaux de disponibilité restent limités aux annonces capturées."
    if seller_count:
        return (
            f"Pour {product_name}, la vue des prix de détail en Tunisie inclut actuellement {seller_count} référence(s) vendeur, "
            f"ce qui suggère une densité visible {density}. {competition} {availability}"
        )
    return (
        f"Pour {product_name}, la validation du marché tunisien reste faible car aucune référence de prix de détail avec prix confirmé n'a été trouvée. "
        f"{competition} {availability}"
    )


def _fallback_business_reading_en(
    product_name: str,
    profitability: ProfitabilityEstimate,
    recommendation: str,
    recommendation_reason: str,
) -> str:
    margin_text = (
        f"Estimated gross margin before marketing is {profitability.gross_margin_per_unit_before_marketing_tnd:g} TND/unit"
        if profitability.gross_margin_per_unit_before_marketing_tnd is not None
        else "Gross margin before marketing could not be confirmed yet"
    )
    return (
        f"Business reading for {product_name}: recommendation is {recommendation.replace('_', ' ')}. "
        f"{margin_text}. {recommendation_reason}"
    )


def _fallback_business_reading_fr(
    product_name: str,
    profitability: ProfitabilityEstimate,
    recommendation: str,
    recommendation_reason: str,
) -> str:
    margin_text = (
        f"La marge brute estimée est de {_format_number(profitability.gross_margin_per_unit_before_marketing_tnd)} TND/unité"
        if profitability.gross_margin_per_unit_before_marketing_tnd is not None
        else "La marge brute ne peut pas encore être confirmée"
    )
    return (
        f"Lecture business pour {product_name} : la recommandation est {recommendation.replace('_', ' ')}. "
        f"{margin_text}. {recommendation_reason}"
    )


def _china_link(offer: ChinaSourcingOffer, cost_config: CostConfig, evidence: ProviderEvidence) -> PrototypeSourcingLink:
    price = offer.price_range_usd
    if offer.price_min_usd_numeric is not None:
        min_tnd = offer.price_min_usd_numeric * cost_config.usd_to_tnd_rate
        if offer.price_max_usd_numeric is not None:
            max_tnd = offer.price_max_usd_numeric * cost_config.usd_to_tnd_rate
            price = f"{min_tnd:.2f} TND - {max_tnd:.2f} TND"
        else:
            price = f"{min_tnd:.2f} TND"
    return PrototypeSourcingLink(
        title=offer.product_title or offer.name,
        url=offer.source_url,
        price=price,
        moq=offer.moq,
        confidence=offer.confidence,
        evidence_sources=[source.model_dump() for source in _sources_for_offer(offer.source_url, evidence)],
    )


def _tunisia_link(offer: TunisiaSourcingOffer) -> PrototypeSourcingLink:
    return PrototypeSourcingLink(
        title=offer.product_title or offer.name,
        url=offer.source_url,
        price=offer.price_range_tnd,
        confidence=offer.confidence,
    )


def _valid_image_or_none(url: str | None, evidence: ProviderEvidence, product: ProductUnderstanding) -> str | None:
    if url and _is_product_image_url(url):
        source = _source_for_image(url, evidence)
        if source and _image_source_matches_product(source, product):
            return url
    selected = _best_source_image(evidence, product)
    return selected[1] if selected else None


def _image_payload(url: str | None, evidence: ProviderEvidence, product: ProductUnderstanding) -> dict:
    if url and _is_product_image_url(url):
        source = _source_for_image(url, evidence)
        if source and _image_source_matches_product(source, product):
            return {
                "product_image_url": url,
                "product_image_source_url": source.url,
                "product_image_confidence": _image_confidence(source, product),
                "product_image_notes": "Source-backed image selected from provider evidence.",
            }
    selected = _best_source_image(evidence, product)
    if selected:
        source, image_url = selected
        return {
            "product_image_url": image_url,
            "product_image_source_url": source.url,
            "product_image_confidence": _image_confidence(source, product),
            "product_image_notes": "Source-backed image selected from provider evidence.",
        }
    return {
        "product_image_url": None,
        "product_image_source_url": None,
        "product_image_confidence": "fallback",
        "product_image_notes": "No reliable source-backed product image was found.",
    }


def _landed_cost_breakdown(source_unit_price: float | None, cost_config: CostConfig) -> tuple[float | None, str, dict[str, float | None]]:
    parts: dict[str, float | None] = {
        "shipping": None,
        "customs": None,
        "handling": None,
        "misc": None,
    }
    if source_unit_price is None:
        return None, "Estimated landed cost requires a source-backed unit price.", parts

    shipping = float(cost_config.default_shipping_per_unit_tnd or 0)
    customs = round(source_unit_price * float(cost_config.default_customs_or_import_rate_percent or 0) / 100, 2)
    handling = float(cost_config.default_handling_per_unit_tnd or 0)
    misc = float(cost_config.default_misc_cost_per_unit_tnd or 0)
    parts.update(
        {
            "shipping": shipping,
            "customs": customs,
            "handling": handling,
            "misc": misc,
        }
    )
    if shipping == 0 and customs == 0 and handling == 0 and misc == 0:
        return (
            None,
            "Estimated landed cost requires shipping/import/handling assumptions.",
            parts,
        )
    landed = round(source_unit_price + shipping + customs + handling + misc, 2)
    note = (
        f"Supplier price equivalent to the target package {source_unit_price:g} TND + shipping {shipping:g} TND "
        f"+ customs/import {customs:g} TND + handling {handling:g} TND "
        f"+ misc {misc:g} TND = estimated landed cost {landed:g} TND/unit. "
        "Shipping, customs, handling, and misc values are admin assumptions unless source-backed."
    )
    return landed, note, parts


def _landed_cost_breakdown_range(
    source_min: float | None,
    source_max: float | None,
    cost_config: CostConfig,
) -> tuple[float | None, float | None, str, dict[str, float | None]]:
    """Calculate the full source-price interval without collapsing evidence to a raw minimum."""
    if source_min is None or source_max is None:
        landed, note, parts = _landed_cost_breakdown(source_min, cost_config)
        return landed, landed, note, parts
    shipping = float(cost_config.default_shipping_per_unit_tnd or 0)
    handling = float(cost_config.default_handling_per_unit_tnd or 0)
    misc = float(cost_config.default_misc_cost_per_unit_tnd or 0)
    customs_rate = float(cost_config.default_customs_or_import_rate_percent or 0) / 100
    if shipping == 0 and handling == 0 and misc == 0 and customs_rate == 0:
        return None, None, "Le coût rendu ne peut pas encore être estimé : les hypothèses de transport, d’import et de manutention sont absentes.", {"shipping": 0, "customs": 0, "handling": 0, "misc": 0}
    min_customs = round(source_min * customs_rate, 2)
    max_customs = round(source_max * customs_rate, 2)
    landed_min = round(source_min + shipping + min_customs + handling + misc, 2)
    landed_max = round(source_max + shipping + max_customs + handling + misc, 2)
    parts = {
        "shipping": shipping,
        "customs": min_customs,
        "handling": handling,
        "misc": misc,
    }
    note = (
        f"Prix fournisseur comparable : {source_min:g} TND à {source_max:g} TND par unité ; "
        f"coût rendu : {landed_min:g} TND à {landed_max:g} TND par unité. "
        "Transport, droits/taxes, manutention et autres charges sont des hypothèses estimées."
    )
    return landed_min, landed_max, note, parts


def _enrichment_fields(
    validated: ProviderAnalysisResult,
    evidence: ProviderEvidence,
    cost_config: CostConfig,
    profitability: ProfitabilityEstimate,
    product: ProductUnderstanding,
) -> dict:
    return {
        "china_offers": _china_offer_views(validated.china_sourcing_offers, cost_config, product),
        "tunisia_wholesale_offers": _tunisia_wholesale_offer_views(validated.tunisia_sourcing_offers),
        "retail_offers": _retail_offer_views(validated.tunisia_retail_market.retail_offers, product),
        "landed_cost": _landed_cost_view(profitability),
        "comparability": _comparability_assessment(product, validated),
        "competition_level": _competition_level(validated, product),
        "detailed_scoring": _detailed_scoring(validated, profitability, product),
        "commercial_potential_score": _commercial_potential_score(validated, product),
        "ads_potential_score": None,
        "sources": _source_references(validated, evidence),
    }


def _china_offer_views(
    offers: list[ChinaSourcingOffer],
    cost_config: CostConfig,
    product: ProductUnderstanding | None = None,
) -> list[SourcingOfferView]:
    views: list[SourcingOfferView] = []
    for offer in offers:
        rate = float(cost_config.usd_to_tnd_rate or 0)
        min_tnd = round(offer.price_min_usd_numeric * rate, 2) if offer.price_min_usd_numeric is not None and rate > 0 else None
        max_tnd = round(offer.price_max_usd_numeric * rate, 2) if offer.price_max_usd_numeric is not None and rate > 0 else None
        equivalent_price, comparability_note = _supplier_target_package_price(offer, cost_config, product)
        views.append(SourcingOfferView(
            name=offer.name,
            supplier_type=offer.type,
            product_title=offer.product_title,
            price_text=offer.price_range_usd,
            price_min=offer.price_min_usd_numeric,
            price_max=offer.price_max_usd_numeric,
            price_unit=offer.price_unit,
            currency="USD" if (offer.price_min_usd_numeric is not None or offer.price_max_usd_numeric is not None or offer.price_range_usd) else "",
            price_min_tnd=min_tnd,
            price_max_tnd=max_tnd,
            moq=offer.moq,
            source_url=offer.source_url,
            confidence=offer.confidence,
            product_match=offer.product_match,
            match_notes=offer.match_notes,
            comparable=equivalent_price is not None,
            equivalent_target_package_price_tnd=equivalent_price,
            comparability_note=comparability_note,
        ))
    return views


def _tunisia_wholesale_offer_views(offers: list[TunisiaSourcingOffer]) -> list[SourcingOfferView]:
    return [
        SourcingOfferView(
            name=offer.name,
            supplier_type=offer.type,
            product_title=offer.product_title,
            price_text=offer.price_range_tnd,
            price_min=offer.price_min_tnd_numeric,
            price_max=offer.price_max_tnd_numeric,
            currency="TND",
            price_min_tnd=offer.price_min_tnd_numeric,
            price_max_tnd=offer.price_max_tnd_numeric,
            moq=None,
            source_url=offer.source_url,
            confidence=offer.confidence,
            product_match=offer.product_match,
            match_notes=offer.match_notes,
        )
        for offer in offers
    ]


def _retail_offer_views(
    offers: list,
    product: ProductUnderstanding | None = None,
) -> list[RetailOfferView]:
    views: list[RetailOfferView] = []
    for offer in offers:
        volume_quantity, volume_unit = _parse_volume(offer.product_title or "")
        normalized = None
        normalization_note = ""
        base_price = offer.price_min_tnd_numeric
        if base_price is not None and volume_quantity is not None:
            liters = _unit_to_liters(volume_unit)
            kilograms = _unit_to_kilograms(volume_unit)
            if liters is not None and liters > 0:
                normalized_volume = volume_quantity * liters
                normalized = round(base_price / normalized_volume, 2)
                normalization_note = f"{_format_number(base_price)} TND / {_format_number(volume_quantity)} L = {_format_number(normalized)} TND/L"
            elif kilograms is not None and kilograms > 0:
                normalized_volume = volume_quantity * kilograms
                normalized = round(base_price / normalized_volume, 2)
                normalization_note = f"{_format_number(base_price)} TND / {_format_number(volume_quantity)} kg = {_format_number(normalized)} TND/kg"
        # Recalculate from the retained total price and package volume whenever
        # both are available. Model-provided normalized values may repeat the
        # total package price and inflate the comparable market reference.
        if normalized is None and volume_quantity is not None and offer.normalized_price_numeric is not None:
            normalized = offer.normalized_price_numeric
            normalization_note = offer.price_normalization_notes or "Normalized price supplied by the research validation layer."
        comparable_target_price = _retail_target_package_price(offer, product)
        if comparable_target_price is not None and product is not None:
            target_volume, target_unit = _product_target_volume(product)
            offer_volume = _base_volume(volume_quantity, volume_unit)
            if target_volume and target_unit and offer_volume and offer_volume != target_volume:
                normalization_note = (
                    f"Prix observé : {_format_number(base_price)} TND / {_format_number(volume_quantity)}{volume_unit}. "
                    f"Équivalent normalisé { _format_number(target_volume) }{target_unit} : "
                    f"{_format_money(comparable_target_price)} TND."
                ).replace("  ", " ")
        views.append(RetailOfferView(
            seller_name=offer.seller_name,
            brand=_extract_brand(offer.product_title or ""),
            product_title=offer.product_title,
            volume_text=f"{_format_number(volume_quantity)}{volume_unit}" if volume_quantity is not None else "",
            price_tnd=offer.price_min_tnd_numeric,
            price_range_tnd=offer.price_range_tnd,
            normalized_price_text=normalization_note,
            normalized_price_per_unit_tnd=normalized,
            availability="",
            city=_extract_city(offer.seller_name),
            price_type=offer.source_price_type,
            page_type=offer.source_page_type,
            source_url=offer.source_url,
            confidence=offer.confidence,
            product_match=offer.product_match,
            comparable=comparable_target_price is not None,
            comparable_target_price_tnd=comparable_target_price,
            comparability_note=(
                "Comparable au format cible après normalisation."
                if comparable_target_price is not None
                else "NON COMPARABLE : volume/conditionnement non confirmé pour le format cible."
            ) if product is not None else "",
        ))
    return views


def _retail_target_package_price(
    offer,
    product: ProductUnderstanding | None,
) -> float | None:
    if product is None or offer.price_min_tnd_numeric is None:
        return None
    target_volume, target_unit = _product_target_volume(product)
    offer_quantity, offer_unit = _parse_volume(offer.product_title or "")
    offer_volume = _base_volume(offer_quantity, offer_unit)
    offer_base_unit = _base_unit(offer_unit)
    if not target_volume or not target_unit:
        return offer.price_min_tnd_numeric if offer_volume is None else None
    if not target_volume or not target_unit or not offer_volume or offer_base_unit != target_unit:
        return None
    return round(offer.price_min_tnd_numeric / offer_volume * target_volume, 2)


def _supplier_target_package_price(
    offer: ChinaSourcingOffer,
    cost_config: CostConfig,
    product: ProductUnderstanding | None,
) -> tuple[float | None, str]:
    if product is None:
        return None, ""
    if offer.price_min_usd_numeric is None:
        return None, "NON COMPARABLE : prix fournisseur non confirmé."
    target_volume, target_unit = _product_target_volume(product)
    unit_kind = _supplier_price_unit_kind(offer.price_unit)
    price_tnd = round(offer.price_min_usd_numeric * cost_config.usd_to_tnd_rate, 2)
    if unit_kind == "liter" and target_unit == "L" and target_volume:
        return round(price_tnd * target_volume, 2), "Prix fournisseur normalisé au conditionnement cible."
    if unit_kind == "unit":
        declared_volume, declared_unit = _parse_volume(offer.price_unit or "")
        if (
            target_volume
            and target_unit
            and declared_volume is not None
            and _base_volume(declared_volume, declared_unit) == target_volume
            and _base_unit(declared_unit) == target_unit
        ):
            return price_tnd, "Prix fournisseur explicitement indiqué pour le conditionnement cible."
        offer_volume, offer_unit = _parse_volume(offer.product_title or "")
        offer_base_unit = _base_unit(offer_unit)
        if not target_volume or not target_unit or (
            offer_volume is not None
            and _base_volume(offer_volume, offer_unit) == target_volume
            and offer_base_unit == target_unit
        ):
            return price_tnd, "Prix fournisseur par unité du conditionnement cible."
    return None, "NON COMPARABLE : l’unité fournisseur ne peut pas être convertie de façon fiable au conditionnement cible."


KNOWN_BRANDS = (
    "total", "shell", "castrol", "motul", "mannol", "yacco", "elf", "mobil",
    "liqui moly", "valvoline", "repsol", "petronas", "eni", "ipone", "putoline",
    "vitol", "axo", "petromin", "wolf", "bardahl", "fuchs", "texaco", "chevron",
    "millers oils", "gulf", "aral", "esso",
)


def _extract_brand(title: str) -> str:
    lowered = title.lower()
    for brand in KNOWN_BRANDS:
        if re.search(rf"\b{re.escape(brand)}\b", lowered):
            return brand.title()
    return ""


TUNISIAN_CITIES = ("tunis", "sfax", "sousse", "bizerte", "ariana", "ben arous", "monastir", "nabeul", "gabes", "kairouan")


def _extract_city(text: str) -> str:
    lowered = text.lower()
    for city in TUNISIAN_CITIES:
        if re.search(rf"\b{re.escape(city)}\b", lowered):
            return city.title()
    return ""


VOLUME_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ml|l\b|ltr|litres?|liters?|kg|kgs|g\b|gr\b|pcs\.?|pieces?|units?|unités?|pack|packs)", re.IGNORECASE)


def _parse_volume(title: str) -> tuple[float | None, str]:
    match = VOLUME_RE.search(title)
    if not match:
        return None, ""
    quantity = float(str(match.group(1)).replace(",", "."))
    unit = match.group(2).lower().rstrip(".")
    unit_map = {
        "ml": "ml", "l": "L", "ltr": "L", "litre": "L", "litres": "L",
        "liter": "L", "liters": "L", "kg": "kg", "kgs": "kg",
        "g": "g", "gr": "g", "pcs": "pcs", "piece": "pcs", "pieces": "pcs",
        "unit": "pcs", "units": "pcs", "unités": "pcs",
        "pack": "pack", "packs": "pack",
    }
    return quantity, unit_map.get(unit, unit.upper() if len(unit) <= 3 else unit)


def _unit_to_liters(unit: str) -> float | None:
    if unit == "ml":
        return 0.001
    if unit == "L":
        return 1.0
    return None


def _unit_to_kilograms(unit: str) -> float | None:
    if unit == "g":
        return 0.001
    if unit == "kg":
        return 1.0
    return None


def _format_number(value: float | None) -> str:
    if value is None:
        return "-"
    formatted = f"{value:.2f}".rstrip("0").rstrip(".")
    return formatted.replace(".", ",")


def _format_money(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}".replace(".", ",")


def _landed_cost_view(profitability: ProfitabilityEstimate) -> LandedCostView:
    components: list[LandedCostComponentView] = []
    source_price = profitability.source_unit_price_tnd
    shipping = profitability.estimated_shipping_per_unit_tnd
    customs = profitability.estimated_customs_per_unit_tnd
    handling = profitability.estimated_handling_per_unit_tnd
    misc = profitability.estimated_misc_per_unit_tnd
    total = profitability.estimated_landed_cost_per_unit_tnd
    components.append(LandedCostComponentView(
        label_key="supplier_price",
        value_tnd=source_price,
        provenance="observed" if source_price is not None else "unavailable",
    ))
    components.append(LandedCostComponentView(
        label_key="shipping",
        value_tnd=shipping,
        provenance="estimate" if shipping is not None else "unavailable",
    ))
    components.append(LandedCostComponentView(
        label_key="customs",
        value_tnd=customs,
        provenance="computed" if customs is not None else "unavailable",
        note="Applied on supplier price using configured import rate.",
    ))
    components.append(LandedCostComponentView(
        label_key="handling",
        value_tnd=handling,
        provenance="estimate" if handling not in (None, 0) else "unavailable",
    ))
    components.append(LandedCostComponentView(
        label_key="misc",
        value_tnd=misc,
        provenance="estimate" if misc not in (None, 0) else "unavailable",
    ))
    partial = total is None or any(component.provenance in ("estimate", "unavailable") for component in components)
    note = profitability.landed_cost_breakdown_notes or (
        "Estimation partielle — certaines charges d'importation ne sont pas incluses."
        if partial else ""
    )
    minimum = profitability.estimated_landed_cost_min_tnd
    maximum = profitability.estimated_landed_cost_max_tnd
    range_text = _range_text("TND", [minimum, maximum]) if minimum is not None and maximum is not None else ""
    for component in components:
        if component.label_key == "supplier_price":
            component.min_tnd = profitability.source_unit_price_min_tnd
            component.max_tnd = profitability.source_unit_price_max_tnd
        elif component.label_key == "customs" and profitability.source_unit_price_min_tnd is not None:
            rate = (
                customs / profitability.source_unit_price_min_tnd
                if customs is not None and profitability.source_unit_price_min_tnd
                else None
            )
            component.min_tnd = round(profitability.source_unit_price_min_tnd * rate, 2) if rate is not None else customs
            component.max_tnd = (
                round(profitability.source_unit_price_max_tnd * rate, 2)
                if rate is not None and profitability.source_unit_price_max_tnd is not None
                else customs
            )
        else:
            component.min_tnd = component.value_tnd
            component.max_tnd = component.value_tnd
        if component.min_tnd is not None and component.max_tnd is not None:
            component.range_text = _range_text("TND", [component.min_tnd, component.max_tnd])
    return LandedCostView(total_tnd=total, min_tnd=minimum, max_tnd=maximum, range_text=range_text, components=components, partial_estimate=partial, note=note)


def _comparability_assessment(product: ProductUnderstanding, validated: ProviderAnalysisResult) -> ComparabilityAssessment:
    reasons: list[str] = []
    score = 50

    sourcing_titles = [
        (offer.product_title or offer.name).lower()
        for offer in [*validated.china_sourcing_offers, *validated.tunisia_sourcing_offers]
        if (offer.product_title or offer.name)
    ]
    retail_titles = [
        (offer.product_title or "").lower()
        for offer in validated.tunisia_retail_market.retail_offers
        if offer.product_title
    ]

    key_terms = [term.lower() for term in product.must_include_terms + product.technical_specs if term.strip()]
    key_terms.extend(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", product.normalized_product.lower()))
    key_terms = [term for term in set(key_terms) if len(term) >= 2]

    overlap_found = False
    for title in sourcing_titles:
        matches = sum(1 for term in key_terms if term in title)
        if matches >= max(1, min(2, len(key_terms))):
            overlap_found = True
            break
    if overlap_found:
        score += 20
        reasons.append("Sourced products share key characteristics with the analyzed product.")
    else:
        score -= 15
        reasons.append("Sourced products only partially match the requested product characteristics.")

    sourcing_volumes = [_parse_volume(title) for title in sourcing_titles]
    retail_volumes = [_parse_volume(title) for title in retail_titles]
    sourcing_units = {unit for _, unit in sourcing_volumes if unit}
    retail_units = {unit for _, unit in retail_volumes if unit}
    same_unit = bool(sourcing_units & retail_units)
    comparable_unit = bool({"L", "ml"} <= (sourcing_units | retail_units)) or bool({"kg", "g"} <= (sourcing_units | retail_units))

    if sourcing_volumes and retail_volumes and same_unit:
        sourcing_sizes = sorted({quantity for quantity, _ in sourcing_volumes if quantity})
        retail_sizes = sorted({quantity for quantity, _ in retail_volumes if quantity})
        if sourcing_sizes == retail_sizes:
            score += 25
            unit_label = next(iter(sourcing_units))
            reasons.append(f"Same packaging volume found on both sides ({_format_number(sourcing_sizes[0])}{unit_label}).")
        else:
            reasons.append(
                "Different packaging volumes detected; margins must be read on the normalized price per litre/kilo."
            )
            if comparable_unit:
                score += 10
            else:
                score -= 10
    elif sourcing_volumes or retail_volumes:
        reasons.append("Volume information is only available on one side; use the normalized price per unit when possible.")
        score += 5
    else:
        reasons.append("No explicit volume was detected; prices are compared per unit as listed.")
        score -= 5

    if not sourcing_titles or not retail_titles:
        score -= 30
        reasons.append("One side of the comparison has no priced offers, so equivalence cannot be verified.")

    score = max(0, min(100, score))
    quality_terms = " ".join([*sourcing_titles, *retail_titles])
    quality_verified = bool(re.search(r"\b(?:api|acea)\b", quality_terms, re.IGNORECASE))
    if score >= 70 and not quality_verified:
        score = 69
        reasons.append("API/ACEA or equivalent quality positioning was not verified.")
    if score >= 70:
        level = "high"
    elif score >= 40:
        level = "medium"
    else:
        level = "low"

    normalization_note = (
        "Prices are compared per unit after normalisation (TND/litre or TND/kg) whenever volumes differ."
        if level != "low"
        else "Prices cannot be reliably normalized between the two sides."
    )
    return ComparabilityAssessment(
        level=level,
        score=score,
        reasons=reasons,
        normalization_note=normalization_note,
        margin_is_indicative_only=level == "low",
    )


def _competition_level(validated: ProviderAnalysisResult, product: ProductUnderstanding | None = None) -> str:
    retail = validated.tunisia_retail_market
    relevant_offers = [offer for offer in retail.retail_offers if product is None or _retail_target_package_price(offer, product) is not None]
    sellers = {offer.seller_name.lower() for offer in relevant_offers if offer.seller_name}
    brands = {_extract_brand(offer.product_title or "").lower() for offer in relevant_offers}
    brands.discard("")
    # A small result set is insufficient coverage, not proof of low competition.
    if len(sellers) < 3:
        return "unknown"
    signals = len(sellers) + len(brands)
    if not relevant_offers:
        return "unknown"
    if signals >= 8:
        return "high"
    if signals >= 4:
        return "medium"
    return "low"


def _competition_note(level: str) -> str:
    return {
        "unknown": "Competition data is insufficient; the observed seller coverage is too limited to infer competition intensity.",
        "low": "Few competing sellers or brands were observed.",
        "medium": "A moderate number of competing sellers or brands were observed.",
        "high": "Many established sellers or brands compete on this product.",
    }.get(level, "Competition data is insufficient.")


RECURRENCE_KEYWORDS = ("huile", "oil", "filtre", "filter", "detergent", "savon", "piles", "battery", "consommable", "lubrifi")


def _offers_look_recurring(validated: ProviderAnalysisResult) -> bool:
    titles = " ".join([
        offer.product_title or ""
        for offer in [
            *validated.china_sourcing_offers,
            *validated.tunisia_retail_market.retail_offers,
        ]
    ]).lower()
    return any(keyword in titles for keyword in RECURRENCE_KEYWORDS)


def _margin_percent(profitability: ProfitabilityEstimate | None) -> float | None:
    if not profitability:
        return None
    margin = profitability.gross_margin_per_unit_before_marketing_tnd
    selling = profitability.estimated_selling_price_tnd
    if margin is None or selling in (None, 0):
        return None
    return margin / selling * 100


def _detailed_scoring(validated: ProviderAnalysisResult, profitability: ProfitabilityEstimate | None, product: ProductUnderstanding | None = None) -> DetailedScoring:
    retail = validated.tunisia_retail_market
    comparable_retail = _retail_target_package_prices(retail.retail_offers, product) if product else [
        offer.price_min_tnd_numeric for offer in retail.retail_offers if offer.price_min_tnd_numeric is not None
    ]
    unique_sellers = {offer.seller_name.lower() for offer in retail.retail_offers if offer.seller_name and (not product or _retail_target_package_price(offer, product) is not None)}

    demand_score = min(25, len(unique_sellers) * 5 + min(len(comparable_retail), 5))
    demand_note = (
        f"{len(unique_sellers)} vendeur(s) distinct(s) et {len(comparable_retail)} référence(s) retail comparable(s) observés."
        if comparable_retail else "Aucune référence de prix de détail tunisienne comparable observée."
    )

    margin_percent = _margin_percent(profitability)
    if margin_percent is None:
        margin_score, margin_note = 0, "Marge non calculable : l’unité du prix fournisseur n’est pas confirmée ou le marché comparable manque."
    elif margin_percent >= 30:
        margin_score, margin_note = 25, f"La marge brute représente environ {margin_percent:.0f} % du prix de vente."
    elif margin_percent >= 20:
        margin_score, margin_note = 18, f"La marge brute représente environ {margin_percent:.0f} % du prix de vente."
    elif margin_percent >= 10:
        margin_score, margin_note = 10, f"La marge brute représente environ {margin_percent:.0f} % du prix de vente ; la sécurité reste limitée."
    elif margin_percent > 0:
        margin_score, margin_note = 5, f"La marge brute ne représente qu’environ {margin_percent:.0f} % du prix de vente."
    else:
        margin_score, margin_note = 0, "La marge brute est nulle ou négative."

    if margin_percent is not None:
        margin_penalty = _margin_confidence_penalty(validated, profitability)
        margin_score = max(0, margin_score - margin_penalty)
        if margin_score > 0:
            margin_note = (
                f"La marge brute représente environ {margin_percent:.0f} % du prix de vente. "
                f"Le score économique est réduit de {margin_penalty} point(s) pour fiabilité des données."
            )

    comparable_supplier_count = sum(
        1 for offer in validated.china_sourcing_offers
        if offer.source_url and offer.confidence in {"high", "medium"}
        and (product is None or _supplier_target_package_price(offer, CostConfig(), product)[0] is not None)
    )
    comparable_confidences = [
        offer.confidence for offer in validated.china_sourcing_offers
        if offer.source_url and (product is None or _supplier_target_package_price(offer, CostConfig(), product)[0] is not None)
    ]
    if "high" in comparable_confidences and comparable_supplier_count >= 2:
        sourcing_score, sourcing_note = 18, f"{comparable_supplier_count} offre(s) de sourcing comparable(s) avec preuves solides."
    elif comparable_supplier_count:
        sourcing_score, sourcing_note = 12, f"{comparable_supplier_count} offre(s) de sourcing comparable(s) ; la logistique reste estimée."
    else:
        sourcing_score, sourcing_note = 0, "Aucune offre de sourcing fiable trouvée."

    competition_level = _competition_level(validated, product)
    competition_scores = {"unknown": 0, "low": 8, "medium": 6, "high": 3}
    competition_note = {
        "unknown": "Intensité concurrentielle non déterminable avec la couverture observée.",
        "low": "Peu de vendeurs ou de marques concurrents observés.",
        "medium": "Nombre modéré de vendeurs ou de marques concurrents observés.",
        "high": "De nombreux vendeurs ou marques établis concurrencent ce produit.",
    }[competition_level]

    recurring = _offers_look_recurring(validated)
    recurrence_score = 8 if recurring else 5
    recurrence_note = (
        "Le produit présente des signaux de réachat ou de consommation récurrente."
        if recurring else "La fréquence de réachat reste incertaine selon les preuves disponibles."
    )

    risk_score, risk_note = _risk_management_score(validated, profitability, len(unique_sellers))

    criteria = [
        ScoreCriterion(key="market_demand", score=demand_score, max_score=25, justification=demand_note),
        ScoreCriterion(key="margin", score=margin_score, max_score=25, justification=margin_note),
        ScoreCriterion(key="sourcing", score=sourcing_score, max_score=20, justification=sourcing_note),
        ScoreCriterion(key="competition", score=competition_scores[competition_level], max_score=10, justification=competition_note),
        ScoreCriterion(key="recurrence", score=recurrence_score, max_score=10, justification=recurrence_note),
        ScoreCriterion(key="risk", score=risk_score, max_score=10, justification=risk_note),
    ]
    return DetailedScoring(total=min(100, sum(c.score for c in criteria)), criteria=criteria)


def _margin_confidence_penalty(
    validated: ProviderAnalysisResult,
    profitability: ProfitabilityEstimate | None,
) -> int:
    if profitability is None or profitability.gross_margin_per_unit_before_marketing_tnd is None:
        return 0
    selected = _canonical_supplier_offer(validated)
    penalty = 2 if selected and selected.confidence == "low" else 0
    if profitability.estimated_landed_cost_per_unit_tnd is not None:
        penalty += 1
    if not validated.tunisia_sourcing_offers:
        penalty += 1
    if _overall_confidence(validated) == "low":
        penalty += 1
    return min(penalty, 20)


def _risk_management_score(
    validated: ProviderAnalysisResult,
    profitability: ProfitabilityEstimate | None,
    seller_count: int,
) -> tuple[int, str]:
    score = 10
    limits: list[str] = []
    risk_limits = [
        (_overall_confidence(validated) == "low", 3, "confiance globale faible"),
        (not profitability or not profitability.source_price_unit_confirmed, 3, "unité du prix fournisseur inconnue"),
        (sum(1 for offer in validated.china_sourcing_offers if offer.source_url and (profitability is None or offer.price_unit)) < 3, 2, "moins de trois fournisseurs comparables"),
        (seller_count < 3 or _competition_level(validated) == "unknown", 2, "couverture de la concurrence insuffisante"),
    ]
    for limited, deduction, label in risk_limits:
        if limited:
            score -= deduction
            limits.append(label)
    if not limits:
        return score, "La maîtrise du risque est soutenue par une couverture suffisante des preuves."
    return max(0, score), "Maîtrise du risque limitée : " + "; ".join(limits) + "."


def _commercial_potential_score(validated: ProviderAnalysisResult, product: ProductUnderstanding | None = None) -> int:
    scoring = _detailed_scoring(validated, None, product)
    by_key = {criterion.key: criterion for criterion in scoring.criteria}
    relevant = [by_key[k] for k in ("market_demand", "competition", "recurrence") if k in by_key]
    max_total = sum(c.max_score for c in relevant)
    raw = sum(c.score for c in relevant)
    return round(raw / max_total * 100) if max_total else 0


def _ads_potential_score(validated: ProviderAnalysisResult) -> int:
    scoring = _detailed_scoring(validated, None)
    by_key = {criterion.key: criterion for criterion in scoring.criteria}
    relevant = [by_key[k] for k in ("market_demand", "ads_potential", "recurrence") if k in by_key]
    max_total = sum(c.max_score for c in relevant)
    raw = sum(c.score for c in relevant)
    return round(raw / max_total * 100) if max_total else 0


def _source_references(validated: ProviderAnalysisResult, evidence: ProviderEvidence) -> list[SourceReference]:
    by_url = {source.url: source for source in evidence.sources if source.url}
    references: list[SourceReference] = []
    seen: set[str] = set()

    def add(url: str, data_used: str) -> None:
        if url in seen:
            return
        seen.add(url)
        source = by_url.get(url)
        references.append(SourceReference(
            title=source.title if source else url,
            url=url,
            data_used=data_used,
            date="",
            type=(source.region_hint if source else "source"),
            confidence="medium" if source else "low",
        ))

    for offer in validated.china_sourcing_offers[:3]:
        if offer.source_url and offer.price_min_usd_numeric is not None and offer.product_title:
            add(offer.source_url, "Fournisseur Chine / prix / MOQ")
    for offer in validated.tunisia_sourcing_offers[:3]:
        if offer.source_url and offer.price_min_tnd_numeric is not None and offer.product_title:
            add(offer.source_url, "Prix grossiste Tunisie")
    for offer in validated.tunisia_retail_market.retail_offers[:4]:
        if offer.source_url and offer.price_min_tnd_numeric is not None and offer.product_title:
            add(offer.source_url, "Prix de détail Tunisie")
    return references[:8]


def _ad_allocation(cost_config: CostConfig) -> tuple[float | None, str]:
    budget = _digital_ad_budget_default(cost_config)
    expected_units = cost_config.default_expected_units_sold_from_campaign
    if budget is None or expected_units is None or expected_units <= 0:
        if budget is not None:
            return None, (
                f"Digital advertising budget assumed at {budget:g} TND total for the scenario. "
                "Per-unit ad allocation is only shown when expected units sold are available."
            )
        return None, "Digital advertising estimate requires a scenario budget assumption."
    allocation = round(float(budget) / float(expected_units), 2)
    return (
        allocation,
        (
            f"Digital advertising allocation: {budget:g} TND total / {expected_units:g} expected units sold "
            f"= {allocation:g} TND per sold unit. This remains an allocation estimate, not a guarantee."
        ),
    )


def _first_source_image(evidence: ProviderEvidence) -> str | None:
    selected = _best_source_image(evidence, ProductUnderstanding())
    return selected[1] if selected else None


def _best_source_image(evidence: ProviderEvidence, product: ProductUnderstanding) -> tuple[ProviderRawSource, str] | None:
    sorted_sources = sorted(evidence.sources, key=lambda source: _image_source_score(source, product), reverse=True)
    for source in sorted_sources:
        if not _image_source_matches_product(source, product):
            continue
        for image_url in _source_image_candidates(source):
            if image_url.startswith(("http://", "https://")):
                return source, image_url
    return None


def _source_for_image(url: str, evidence: ProviderEvidence) -> ProviderRawSource | None:
    for source in evidence.sources:
        if url in _source_image_candidates(source):
            return source
    return None


def _source_image_candidates(source: ProviderRawSource) -> list[str]:
    candidates: list[str] = []
    candidates.extend(source.image_urls)
    for text in (source.snippet, source.content or ""):
        candidates.extend(IMAGE_MARKDOWN_RE.findall(text))
        candidates.extend(IMAGE_HTML_RE.findall(text))
        candidates.extend(META_IMAGE_RE.findall(text))
        candidates.extend(IMAGE_URL_RE.findall(text))
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        cleaned = candidate.strip().rstrip(").,;\"'")
        if not _is_product_image_url(cleaned) or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


def _is_product_image_url(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    path = urlparse(url).path.lower()
    blocked_markers = ("favicon", "/sash/", "/batch/", "uedata", "placeholder", "image-not-found", "no-image", "/logo", "/sprite")
    return not any(marker in path for marker in blocked_markers)


def _image_source_matches_product(source: ProviderRawSource, product: ProductUnderstanding) -> bool:
    source_text = re.sub(
        r"\s+",
        "",
        f"{_source_text(source)} {source.url}".lower().replace("-", ""),
    )
    product_text = " ".join([
        product.original_product or "",
        product.normalized_product or "",
        " ".join(product.technical_specs or []),
    ]).lower().replace("-", "")
    target_viscosities = re.findall(r"\b\d+w\d+\b", product_text)
    if target_viscosities and not all(viscosity in source_text for viscosity in target_viscosities):
        return False
    target_volumes = _product_volume_tokens(product_text)
    if target_volumes and not all(volume in source_text for volume in target_volumes):
        return False
    if target_viscosities and source.source_type not in {"product_page", "search_result"}:
        return False
    product_terms = {"oil", "huile", "engine", "moteur", "lubricant", "automotive"}
    if any(term in product_text for term in product_terms) and not any(term in source_text for term in product_terms):
        return False
    return True


def _product_volume_tokens(product_text: str) -> list[str]:
    normalized = re.sub(r"\s+", "", product_text)
    return [f"{amount}{unit}" for amount, unit in re.findall(
        r"\b(\d+(?:[.,]\d+)?)(l|ml|kg|g|pcs?|pieces?|units?)\b",
        normalized,
    )]


def _image_source_score(source: ProviderRawSource, product: ProductUnderstanding) -> int:
    text = _source_text(source)
    score = 0
    if source.source_type == "product_page":
        score += 4
    if source.region_hint in {"china_sourcing", "tunisia_sourcing", "tunisia_retail"}:
        score += 2
    for term in product.must_include_terms:
        if term.lower() in text:
            score += 2
    if product.brand_or_model and product.brand_or_model.lower() in text:
        score += 3
    return score


def _image_confidence(source: ProviderRawSource | None, product: ProductUnderstanding) -> str:
    if source is None:
        return "low"
    score = _image_source_score(source, product)
    if score >= 6:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def _range_text(prefix: str, values: list[float | None], suffix: str = "") -> str:
    clean = [value for value in values if value is not None]
    if not clean:
        return ""
    currency = suffix.strip() or prefix.strip()
    suffix_text = f" {currency}" if currency else ""
    if min(clean) == max(clean):
        return f"{_format_number(min(clean))}{suffix_text}"
    return f"{_format_number(min(clean))}–{_format_number(max(clean))}{suffix_text}"


def _retail_summary_from_validated(
    validated: ProviderAnalysisResult,
    product: ProductUnderstanding | None = None,
) -> RetailMarketSummary:
    retail = validated.tunisia_retail_market
    seller_density = _computed_seller_density(retail.retail_offers)
    if product is not None:
        comparable_offers = [
            offer for offer in retail.retail_offers
            if _retail_target_package_price(offer, product) is not None
        ]
        retained_prices = [
            _retail_target_package_price(offer, product)
            for offer in comparable_offers
        ]
        summary_offers = retail.retail_offers
    else:
        summary_offers = retail.retail_offers
        retained_prices = [
            offer.price_min_tnd_numeric
            for offer in summary_offers
            if offer.price_min_tnd_numeric is not None
        ]
    retained_prices = [price for price in retained_prices if price is not None]
    retail_min = min(retained_prices) if retained_prices else (retail.price_min_tnd if product is None else None)
    retail_max = max(retained_prices) if retained_prices else (retail.price_max_tnd if product is None else None)
    retail_avg = (
        round(sum(retained_prices) / len(retained_prices), 2)
        if retained_prices
        else (retail.price_avg_tnd if product is None else None)
    )
    return _retail_summary_with_fallbacks(RetailMarketSummary(
        retail_price_range_tnd=_range_text("", [retail_min, retail_max], suffix=" TND"),
        retail_min_tnd=retail_min,
        retail_max_tnd=retail_max,
        retail_avg_tnd=retail_avg,
        seller_density=seller_density,
        example_retail_prices=[
            ExampleRetailPrice(
                seller_name=offer.seller_name,
                product_title=offer.product_title,
                price_tnd=offer.price_min_tnd_numeric,
                price_range_tnd=offer.price_range_tnd,
                source_price_type=offer.source_price_type,
                source_page_type=offer.source_page_type,
                source_url=offer.source_url,
                confidence=offer.confidence,
                comparable=product is None or _retail_target_package_price(offer, product) is not None,
            )
            for offer in summary_offers[:10]
        ],
        competition_notes=_competition_note(_competition_level(validated)),
        availability_notes=retail.availability_notes,
    ))


def _retail_summary_with_fallbacks(summary: RetailMarketSummary) -> RetailMarketSummary:
    if (
        summary.retail_price_range_tnd
        and summary.retail_min_tnd is not None
        and summary.retail_max_tnd is not None
        and summary.retail_avg_tnd is not None
    ):
        return summary
    range_points: list[float] = []
    average_points: list[float] = []
    for item in summary.example_retail_prices:
        values = _example_retail_values(item)
        if not values:
            continue
        range_points.extend(values)
        average_points.append(round(sum(values) / len(values), 2))
    retail_min = summary.retail_min_tnd if summary.retail_min_tnd is not None else (min(range_points) if range_points else None)
    retail_max = summary.retail_max_tnd if summary.retail_max_tnd is not None else (max(range_points) if range_points else None)
    retail_avg = summary.retail_avg_tnd if summary.retail_avg_tnd is not None else (
        round(sum(average_points) / len(average_points), 2) if average_points else None
    )
    retail_range = summary.retail_price_range_tnd or _range_text("", [retail_min, retail_max], suffix=" TND")
    return summary.model_copy(
        update={
            "retail_price_range_tnd": retail_range,
            "retail_min_tnd": retail_min,
            "retail_max_tnd": retail_max,
            "retail_avg_tnd": retail_avg,
        }
    )


def _example_retail_values(item: ExampleRetailPrice) -> list[float]:
    if not item.comparable:
        return []
    if item.price_tnd is not None:
        return [float(item.price_tnd)]
    text = (item.price_range_tnd or "").replace("\u2013", "-")
    numbers = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", text)]
    if not numbers:
        return []
    if len(numbers) == 1:
        return numbers
    return sorted(numbers[:2])


def _tunisia_wholesale_summary(offers: list[TunisiaSourcingOffer]) -> str:
    prices = [offer.price_min_tnd_numeric for offer in offers if offer.price_min_tnd_numeric is not None]
    if not prices:
        return TUNISIA_WHOLESALE_NOT_FOUND
    return f"Des preuves grossiste/importateur/distributeur tunisiennes ont été trouvées entre {min(prices):g} et {max(prices):g} TND par unité."


def _digital_ad_budget_min(cost_config: CostConfig) -> float:
    return DIGITAL_AD_BUDGET_MIN_TND


def _digital_ad_budget_max(cost_config: CostConfig) -> float:
    return DIGITAL_AD_BUDGET_MAX_TND


def _digital_ad_budget_default(cost_config: CostConfig) -> float:
    return DIGITAL_AD_BUDGET_DEFAULT_TND


def _overall_confidence(validated: ProviderAnalysisResult, product: ProductUnderstanding | None = None) -> str:
    supplier_count = sum(
        1 for offer in validated.china_sourcing_offers
        if offer.source_url and offer.confidence in {"high", "medium"}
        and (product is None or _supplier_target_package_price(offer, CostConfig(), product)[0] is not None)
    )
    retail_count = sum(
        1 for offer in validated.tunisia_retail_market.retail_offers
        if offer.source_url and offer.confidence in {"high", "medium"}
        and (product is None or _retail_target_package_price(offer, product) is not None)
    )
    if supplier_count >= 3 and retail_count >= 3:
        return "high"
    if supplier_count >= 2 and retail_count >= 3:
        return "medium"
    return "low" if supplier_count or retail_count else "low"


def _conservative_recommendation(
    current: str,
    gross_margin: float | None,
    validated: ProviderAnalysisResult,
    profitability: ProfitabilityEstimate | None,
    product: ProductUnderstanding | None = None,
) -> tuple[str, str]:
    if gross_margin is not None and gross_margin <= 0:
        return "no_go", "La marge brute estimée est nulle ou négative après prise en compte du coût rendu et de la référence de prix de détail comparable."
    if profitability and profitability.estimated_landed_cost_per_unit_tnd is None:
        return "investigate_more", "La rentabilité reste à valider car le prix fournisseur retenu ne peut pas être normalisé de façon fiable au conditionnement cible."
    if not validated.tunisia_retail_market.retail_offers:
        return "investigate_more", "La rentabilité reste à valider car aucune référence de prix de détail tunisienne comparable n’a été identifiée."
    if _has_equivalent_or_weak_china_sourcing(validated):
        return "investigate_more", "La rentabilité reste à valider car les preuves de sourcing comprennent des offres équivalentes ou faiblement correspondantes."
    if gross_margin is None:
        return "investigate_more", "La rentabilité reste à valider parce que la comparabilité du coût fournisseur et de la référence tunisienne est insuffisante."
    confidence = _overall_confidence(validated, product)
    comparable_supplier_count = sum(
        1 for offer in validated.china_sourcing_offers
        if offer.source_url and offer.confidence in {"high", "medium"}
        and (product is None or _supplier_target_package_price(offer, CostConfig(), product)[0] is not None)
    )
    comparable_retail_count = sum(
        1 for offer in validated.tunisia_retail_market.retail_offers
        if offer.source_url and offer.confidence in {"high", "medium"}
        and (product is None or _retail_target_package_price(offer, product) is not None)
    )
    if confidence == "low" or comparable_supplier_count < 2 or comparable_retail_count < 2:
        return "investigate_more", "La marge brute estimée est positive dans le scénario prudent, mais la confiance et le nombre de références comparables restent insuffisants pour un GO."
    if gross_margin >= 10 and confidence in {"medium", "high"}:
        return "go", "La marge brute estimée est positive et les preuves de prix fournisseur permettent de passer à la vérification du fournisseur et au test d’échantillon."
    if gross_margin > 0:
        return "go_with_conditions", "La marge brute estimée est positive, mais un meilleur niveau de preuve fournisseur et un test limité sont nécessaires avant tout engagement de volume."
    if not validated.tunisia_sourcing_offers:
        return "investigate_more", "Le produit présente un potentiel commercial, mais la compétitivité du sourcing et le positionnement marché doivent encore être renforcés."
    return "investigate_more", "Le produit présente un potentiel commercial, mais les preuves disponibles ne justifient pas encore un GO immédiat."


def _decision_scores(context: DecisionScoreContext) -> DecisionScores:
    confidence = _overall_confidence(context.validated, context.product)
    factors = _decision_factors(context, confidence)
    go_percent = _bounded_go_percent(context, confidence)
    if context.final_recommendation != "go" and go_percent > 40:
        go_percent = 40
    no_go_percent = 100 - go_percent
    dominant_side = _dominant_side(go_percent, no_go_percent)
    return DecisionScores(
        go_percent=go_percent,
        no_go_percent=no_go_percent,
        confidence=confidence,
        go_reason=_go_score_reason(context, confidence),
        no_go_reason=_no_go_score_reason(context, factors),
        score_explanation=_score_explanation(context, go_percent, no_go_percent, dominant_side),
        why_go_score=_why_go_score(context, go_percent),
        why_no_go_score=_why_no_go_score(context, confidence),
        dominant_side=dominant_side,
        what_would_change_the_decision=_what_would_change_the_decision(context),
        main_decision_factors=list(dict.fromkeys(factors))[:5],
    )


def _client_decision_fields(context: DecisionScoreContext, scores: DecisionScores) -> dict:
    return {
        "decision_summary": _decision_summary(context, scores),
        "positive_signals": _positive_signals(context),
        "risk_signals": _risk_signals(context),
        "main_decision_factors": _main_decision_factors(context),
    }


def _decision_summary(context: DecisionScoreContext, scores: DecisionScores) -> str:
    if context.final_recommendation == "go":
        return (
            "Les preuves de prix montrent une marge brute suffisante pour avancer prudemment vers la vérification du fournisseur et le test d’un échantillon."
        )
    if context.final_recommendation == "go_with_conditions":
        return "La marge brute est positive, mais le passage à un volume significatif reste conditionné à la confirmation du fournisseur et à un test limité."
    if context.final_recommendation == "no_go":
        return (
            "Les risques dominent car la marge brute comparable est nulle ou négative face au risque d’exécution."
        )
    if context.gross_margin is None:
        return (
            "Le produit présente des signaux commerciaux positifs, mais la rentabilité reste à valider "
            "car la comparabilité du sourcing ou du marché tunisien est insuffisante."
        )
    if scores.go_percent < scores.no_go_percent:
        return (
            "Le produit présente un potentiel commercial, mais la marge brute comparable ne justifie pas encore un GO immédiat."
        )
    return (
        "Le produit présente des signaux positifs, mais le dossier reste équilibré et nécessite une validation renforcée avant passage à l’échelle."
    )


def _positive_signals(context: DecisionScoreContext) -> list[str]:
    signals: list[str] = []
    retail = context.validated.tunisia_retail_market
    if retail.retail_offers and context.gross_margin is not None and context.gross_margin > 0:
        signals.append("Les prix retail comparables sont supérieurs au coût fournisseur estimé.")
        signals.append("Un espace de marge brute existe avant les coûts variables non confirmés.")
    elif retail.retail_offers:
        signals.append("Des références de prix retail tunisiennes sont disponibles pour comparaison.")
    if context.validated.china_sourcing_offers:
        signals.append("Des options de sourcing en Chine avec prix observés sont disponibles.")
    return signals[:3]


def _risk_signals(context: DecisionScoreContext) -> list[str]:
    signals: list[str] = []
    if not context.validated.tunisia_sourcing_offers:
        signals.append("La compétitivité grossiste locale en Tunisie n’est pas visible dans les preuves.")
    if context.profitability and context.profitability.estimated_landed_cost_per_unit_tnd is None:
        signals.append("La rentabilité reste à valider car le coût fournisseur comparable n’est pas confirmé.")
    if context.gross_margin is None:
        signals.append("La rentabilité reste à valider parce que le coût fournisseur et la référence tunisienne ne sont pas comparables de façon suffisante.")
    elif context.gross_margin <= 0:
        signals.append("La marge estimée est faible ou négative.")
    elif context.gross_margin < 5:
        signals.append("La marge estimée reste faible après prise en compte du coût rendu.")
    if _has_equivalent_or_weak_china_sourcing(context.validated):
        signals.append("Les preuves fournisseur reposent encore sur une correspondance équivalente ou faible.")
    signals.append("La qualité des preuves et la répétabilité du coût rendu doivent encore être vérifiées.")
    return list(dict.fromkeys(signals))[:5]


def _main_decision_factors(context: DecisionScoreContext) -> list[str]:
    factors = [
        "Fourchette de prix retail en Tunisie",
        "Scénario de coût rendu",
        "Qualité des preuves",
        "Compétitivité du sourcing",
        "Différenciation sur le marché",
    ]
    if not context.validated.tunisia_retail_market.retail_offers:
        factors[0] = "Preuves retail tunisiennes manquantes"
    if not context.validated.china_sourcing_offers:
        factors[3] = "Preuves de sourcing Chine manquantes"
    return factors


def _computed_seller_density(retail_offers) -> str:
    seller_keys = {
        _seller_density_key(offer)
        for offer in retail_offers
        if offer.price_min_tnd_numeric is not None or offer.price_range_tnd
    }
    seller_keys.discard("")
    unique_count = len(seller_keys)
    if unique_count == 0:
        return "unknown"
    if unique_count <= 2:
        return "low"
    if unique_count <= 5:
        return "medium"
    return "high"


def _seller_density_key(offer) -> str:
    seller_name = (offer.seller_name or "").strip().lower()
    if seller_name and seller_name not in {"retail seller", "unknown", "seller"}:
        return seller_name
    return _hostname(offer.source_url)


def _bounded_go_percent(context: DecisionScoreContext, confidence: str) -> int:
    go_percent = _starting_go_percent(context)
    for cap in _go_score_caps(context, confidence):
        go_percent = min(go_percent, cap)
    return max(0, min(100, round(go_percent)))


def _dominant_side(go_percent: int, no_go_percent: int) -> str:
    if abs(go_percent - no_go_percent) <= 10:
        return "balanced"
    return "go" if go_percent > no_go_percent else "no_go"


def _starting_go_percent(context: DecisionScoreContext) -> int:
    if context.final_recommendation == "go":
        return 60
    if context.final_recommendation == "go_with_conditions":
        return 45
    if context.final_recommendation == "no_go":
        return 10
    return 35


def _go_score_caps(context: DecisionScoreContext, confidence: str) -> list[int]:
    caps: list[int] = []
    if context.final_recommendation == "no_go":
        caps.append(15)
    if context.gross_margin is None:
        caps.append(30)
    elif context.gross_margin <= 0:
        caps.append(10)
    elif context.gross_margin < 5:
        caps.append(35)
    if context.profitability and context.profitability.estimated_landed_cost_per_unit_tnd is None:
        caps.append(25)
    if not context.validated.tunisia_retail_market.retail_offers:
        caps.append(20)
    if not context.validated.china_sourcing_offers:
        caps.append(25)
    if not context.validated.tunisia_sourcing_offers:
        caps.append(45)
    if _has_equivalent_or_weak_china_sourcing(context.validated):
        caps.append(35)
    if confidence == "low":
        caps.append(30)
    return caps


def _decision_factors(context: DecisionScoreContext, confidence: str) -> list[str]:
    factors = _margin_decision_factors(context.gross_margin)
    if context.profitability and context.profitability.estimated_landed_cost_per_unit_tnd is None:
        factors.append("Le coût rendu estimé est manquant ou incomplet.")
    if not context.validated.tunisia_retail_market.retail_offers:
        factors.append("Les preuves retail tunisiennes sont manquantes.")
    if not context.validated.china_sourcing_offers:
        factors.append("Les preuves de prix du sourcing Chine sont manquantes.")
    if not context.validated.tunisia_sourcing_offers:
        factors.append(TUNISIA_WHOLESALE_NOT_FOUND)
    if _has_equivalent_or_weak_china_sourcing(context.validated):
        factors.append("Les preuves de sourcing Chine reposent sur une correspondance large, faible ou seulement équivalente.")
    if confidence == "low":
        factors.append("La confiance dans les preuves est faible.")
    return factors or [context.recommendation_reason or "Les preuves disponibles justifient une décision prudente."]


def _margin_decision_factors(gross_margin: float | None) -> list[str]:
    if gross_margin is None:
        return ["La marge brute ne peut pas être calculée à partir d’un coût rendu et d’un prix retail comparables."]
    if gross_margin <= 0:
        return ["La marge brute estimée est négative ou trop proche de zéro."]
    if gross_margin < 5:
        return ["La marge brute estimée est positive mais faible face aux variations du coût rendu."]
    return ["La marge brute estimée est positive dans le scénario prudent."]


def _go_score_reason(context: DecisionScoreContext, confidence: str) -> str:
    if context.gross_margin is not None and context.gross_margin > 0 and confidence in {"medium", "high"}:
        return "Les preuves disponibles montrent une marge brute estimée positive dans le scénario prudent."
    return "Une marge positive et des preuves source plus solides permettraient de confirmer un GO."


def _no_go_score_reason(context: DecisionScoreContext, factors: list[str]) -> str:
    if context.recommendation_reason:
        return context.recommendation_reason
    return factors[0] if factors else "La qualité des preuves ou la marge ne permet pas encore un GO sûr."


def _score_explanation(
    context: DecisionScoreContext,
    go_percent: int,
    no_go_percent: int,
    dominant_side: str,
) -> str:
    retail = context.validated.tunisia_retail_market
    profitability = context.profitability
    if context.gross_margin is None:
        return (
            "La rentabilité reste à valider parce que le coût fournisseur comparable ou la référence tunisienne comparable "
            "n’est pas confirmé. Les preuves retail et sourcing disponibles ne suffisent pas encore pour conclure."
        )
    retail_range = _range_text("", [retail.price_min_tnd, retail.price_max_tnd], suffix=" TND") or "une fourchette retail comparable non confirmée"
    landed_cost = (
        f"{profitability.estimated_landed_cost_per_unit_tnd:g} TND/unité"
        if profitability and profitability.estimated_landed_cost_per_unit_tnd is not None
        else "le scénario de coût rendu actuel"
    )
    margin_text = (
        f"{_format_number(context.gross_margin)} TND par unité dans le scénario prudent"
        if context.gross_margin is not None
        else "une rentabilité encore non confirmée"
    )
    if dominant_side == "go":
        return (
            f"Le GO est plus élevé car le prix retail autour de {retail_range} dépasse le coût rendu de {landed_cost}, "
            f"avec une marge brute estimée de {margin_text}. Les preuves de sourcing justifient une vérification fournisseur et un test d’échantillon."
        )
    if context.final_recommendation == "no_go":
        return (
            f"Le NO GO est plus élevé car la marge brute comparable n’est pas suffisamment attractive. "
            f"Le prix retail autour de {retail_range} laisse peu d’espace face à {landed_cost}, tandis que la qualité des preuves et le risque d’exécution réduisent l’intérêt d’avancer maintenant."
        )
    if dominant_side == "balanced":
        return (
            f"Le score reste équilibré car le produit présente un potentiel commercial, mais la marge brute autour de {margin_text} doit encore être consolidée face au sourcing et au risque d’exécution."
        )
    return (
        f"Le NO GO est plus élevé car le potentiel estimé reste limité face au risque d’exécution. "
        f"Le prix retail autour de {retail_range} comparé à {landed_cost} suggère une opportunité possible, mais les preuves ne permettent pas encore un GO immédiat."
    )


def _why_go_score(context: DecisionScoreContext, go_percent: int) -> list[str]:
    retail = context.validated.tunisia_retail_market
    profitability = context.profitability
    reasons: list[str] = []
    if profitability and profitability.estimated_selling_price_tnd is not None and profitability.source_unit_price_tnd is not None:
        reasons.append(
            f"Le prix retail estimé est d’environ {profitability.estimated_selling_price_tnd:g} TND contre "
            f"un prix fournisseur équivalent d’environ {profitability.source_unit_price_tnd:g} TND."
        )
    if context.gross_margin is not None and context.gross_margin > 0:
        reasons.append(
            f"Le scénario prudent laisse une marge brute estimée de {_format_number(context.gross_margin)} TND par unité."
        )
    if retail.retail_offers:
        reasons.append(
            f"{len(retail.retail_offers)} offre(s) retail en Tunisie soutiennent la lecture de la demande et du prix de revente."
        )
    if context.validated.china_sourcing_offers:
        reasons.append(
            f"{len(context.validated.china_sourcing_offers)} offre(s) de sourcing en Chine fournissent des preuves de prix."
        )
    return reasons[:4] or [f"GO retains {go_percent}% because the market still shows some resale potential."]


def _why_no_go_score(context: DecisionScoreContext, confidence: str) -> list[str]:
    profitability = context.profitability
    reasons: list[str] = []
    if context.gross_margin is None:
        reasons.append("La rentabilité reste à valider parce que la comparabilité du sourcing et du marché tunisien est insuffisante.")
    elif context.gross_margin <= 0:
        reasons.append(
            f"La marge brute estimée est de {_format_number(context.gross_margin)} TND par unité dans le scénario prudent, ce qui n’est pas suffisamment attractif."
        )
    elif context.gross_margin < 5:
        reasons.append(
            f"La marge brute estimée est seulement de {_format_number(context.gross_margin)} TND par unité dans le scénario prudent, ce qui laisse une sécurité limitée."
        )
    if not context.validated.tunisia_sourcing_offers:
        reasons.append("La compétitivité grossiste locale en Tunisie n’est pas visible dans les preuves disponibles.")
    if _has_equivalent_or_weak_china_sourcing(context.validated):
        reasons.append("Le sourcing Chine repose sur une correspondance équivalente ou faible, ce qui augmente le risque fournisseur et produit.")
    if confidence == "low":
        reasons.append("La vérification fournisseur et la différenciation marché restent trop faibles pour un GO immédiat.")
    return reasons[:5] or ["Le risque d’exécution reste supérieur au potentiel démontré."]


def _what_would_change_the_decision(context: DecisionScoreContext) -> list[str]:
    actions = [
        f"Confirmer les conditions fournisseur et un devis pour {ANALYSIS_QUANTITY_UNITS} unités.",
        "Comparer au moins deux options de sourcing pour vérifier la compétitivité du prix.",
        "Valider la qualité du produit et son adéquation exacte avec un échantillon.",
        "Confirmer les frais de transport, d’importation et de manutention.",
    ]
    if not context.validated.tunisia_sourcing_offers:
        actions.append("Verify whether the product can be positioned above current Tunisia retail competitors without local wholesale support.")
    if _has_equivalent_or_weak_china_sourcing(context.validated):
        actions.append("Secure a closer exact-match supplier option before committing to volume.")
    return actions[:5]


def _profitability_with_evidence_risks(
    profitability: ProfitabilityEstimate,
    validated: ProviderAnalysisResult,
) -> ProfitabilityEstimate:
    risks = list(dict.fromkeys(profitability.risks + _evidence_risks(validated)))
    gross_margin = profitability.gross_margin_per_unit_before_marketing_tnd
    gross_profit_1000 = (
        round(gross_margin * ANALYSIS_QUANTITY_UNITS, 2)
        if gross_margin is not None
        else profitability.gross_profit_for_1000_before_marketing_tnd
    )
    net_profit_1000 = (
        round(gross_profit_1000 - DIGITAL_AD_BUDGET_DEFAULT_TND, 2)
        if gross_profit_1000 is not None
        else profitability.net_profit_for_1000_after_marketing_tnd
    )
    return profitability.model_copy(
        update={
            "estimated_meta_campaign_budget_tnd": DIGITAL_AD_BUDGET_DEFAULT_TND,
            "digital_ad_budget_min_tnd": DIGITAL_AD_BUDGET_MIN_TND,
            "digital_ad_budget_max_tnd": DIGITAL_AD_BUDGET_MAX_TND,
            "digital_ad_budget_default_tnd": DIGITAL_AD_BUDGET_DEFAULT_TND,
            "gross_profit_for_1000_before_marketing_tnd": gross_profit_1000,
            "net_profit_for_1000_after_marketing_tnd": net_profit_1000,
            "net_profit_for_1000_after_advertising_min_tnd": (
                round(gross_profit_1000 - DIGITAL_AD_BUDGET_MAX_TND, 2)
                if gross_profit_1000 is not None
                else profitability.net_profit_for_1000_after_advertising_min_tnd
            ),
            "net_profit_for_1000_after_advertising_max_tnd": (
                round(gross_profit_1000 - DIGITAL_AD_BUDGET_MIN_TND, 2)
                if gross_profit_1000 is not None
                else profitability.net_profit_for_1000_after_advertising_max_tnd
            ),
            "estimated_profit_for_1000_units_tnd": net_profit_1000,
            "risks": risks,
        }
    )


def _reconcile_profitability_supplier_price(
    profitability: ProfitabilityEstimate,
    validated: ProviderAnalysisResult,
    cost_config: CostConfig,
    product: ProductUnderstanding,
) -> ProfitabilityEstimate:
    # The validated response already carries the complete min/max interval.
    # Never collapse it back to a model-provided or minimum-only scalar.
    if profitability.source_unit_price_min_tnd is not None or profitability.source_unit_price_max_tnd is not None:
        return profitability
    supplier_offer = _canonical_supplier_offer(validated, product)
    supplier_price = _canonical_supplier_price(validated, cost_config, product)
    if not supplier_offer or not supplier_offer.price_unit or supplier_price is None:
        return profitability.model_copy(update={
            "source_price_unit": None,
            "source_price_unit_confirmed": False,
            "source_unit_price_tnd": None,
            "estimated_shipping_per_unit_tnd": None,
            "estimated_customs_per_unit_tnd": None,
            "estimated_handling_per_unit_tnd": None,
            "estimated_misc_per_unit_tnd": None,
            "estimated_landed_cost_per_unit_tnd": None,
            "estimated_source_cost_tnd": None,
            "landed_cost_breakdown_notes": "La rentabilité ne peut pas encore être confirmée car le prix fournisseur retenu n’est pas comparable de façon fiable au conditionnement cible.",
            "gross_margin_per_unit_before_marketing_tnd": None,
            "estimated_margin_per_unit_tnd": None,
            "gross_profit_for_1000_before_marketing_tnd": None,
            "net_profit_for_1000_after_marketing_tnd": None,
            "estimated_profit_for_1000_units_tnd": None,
        })
    if supplier_price is None or supplier_price == profitability.source_unit_price_tnd:
        return profitability
    landed, landed_notes, parts = _landed_cost_breakdown(supplier_price, cost_config)
    selling_price = profitability.estimated_selling_price_tnd
    margin = round(selling_price - landed, 2) if selling_price is not None and landed is not None else None
    gross_profit = round(margin * ANALYSIS_QUANTITY_UNITS, 2) if margin is not None else None
    return profitability.model_copy(update={
        "source_unit_price_tnd": supplier_price,
        "source_price_unit": supplier_offer.price_unit if supplier_offer else None,
        "source_price_unit_confirmed": bool(supplier_offer and supplier_offer.price_unit),
        "estimated_shipping_per_unit_tnd": parts["shipping"],
        "estimated_customs_per_unit_tnd": parts["customs"],
        "estimated_handling_per_unit_tnd": parts["handling"],
        "estimated_misc_per_unit_tnd": parts["misc"],
        "estimated_landed_cost_per_unit_tnd": landed,
        "estimated_source_cost_tnd": landed,
        "landed_cost_breakdown_notes": landed_notes,
        "gross_margin_per_unit_before_marketing_tnd": margin,
        "estimated_margin_per_unit_tnd": margin,
        "gross_profit_for_1000_before_marketing_tnd": gross_profit,
        "net_profit_for_1000_after_marketing_tnd": round(gross_profit - DIGITAL_AD_BUDGET_DEFAULT_TND, 2) if gross_profit is not None else None,
        "estimated_profit_for_1000_units_tnd": round(gross_profit - DIGITAL_AD_BUDGET_DEFAULT_TND, 2) if gross_profit is not None else None,
    })


def _reconcile_profitability_market_price(
    profitability: ProfitabilityEstimate,
    validated: ProviderAnalysisResult,
    cost_config: CostConfig,
    product: ProductUnderstanding,
) -> ProfitabilityEstimate:
    """Keep the final profitability payload aligned with retained retail offers."""
    if profitability.estimated_selling_price_min_tnd is not None and profitability.estimated_selling_price_max_tnd is not None:
        landed_min = profitability.estimated_landed_cost_min_tnd
        landed_max = profitability.estimated_landed_cost_max_tnd
        if landed_min is None or landed_max is None:
            return profitability.model_copy(update={
            "estimated_selling_price_tnd": profitability.estimated_selling_price_tnd or round(median([profitability.estimated_selling_price_min_tnd, profitability.estimated_selling_price_max_tnd]), 2),
                "gross_margin_per_unit_before_marketing_tnd": None,
                "estimated_margin_per_unit_tnd": None,
            })
        selling_min = profitability.estimated_selling_price_min_tnd
        selling_max = profitability.estimated_selling_price_max_tnd
        margin_min = round(selling_min - landed_max, 2)
        margin_max = round(selling_max - landed_min, 2)
        prudent = margin_min
        scalar_margin = profitability.gross_margin_per_unit_before_marketing_tnd or round((selling_min + selling_max) / 2 - (profitability.estimated_landed_cost_min_tnd or landed_min), 2)
        gross_profit = round(scalar_margin * ANALYSIS_QUANTITY_UNITS, 2)
        budget = profitability.digital_ad_budget_default_tnd or DIGITAL_AD_BUDGET_DEFAULT_TND
        return profitability.model_copy(update={
            "estimated_selling_price_tnd": profitability.estimated_selling_price_tnd or round(median([selling_min, selling_max]), 2),
            "gross_margin_per_unit_before_marketing_tnd": scalar_margin,
            "gross_margin_min_tnd": margin_min,
            "gross_margin_max_tnd": margin_max,
            "gross_margin_percent_min": round(margin_min / selling_min * 100, 1) if selling_min else None,
            "gross_margin_percent_max": round(margin_max / selling_max * 100, 1) if selling_max else None,
            "estimated_margin_per_unit_tnd": scalar_margin,
            "gross_profit_for_1000_before_marketing_tnd": gross_profit,
            "net_profit_for_1000_after_marketing_tnd": round(gross_profit - budget, 2),
            "estimated_profit_for_1000_units_tnd": round(gross_profit - budget, 2),
        })
    _, selling_price, pricing_basis = _comparable_prices(validated, cost_config, product)
    landed_cost = profitability.estimated_landed_cost_per_unit_tnd
    if selling_price is None or landed_cost is None:
        return profitability.model_copy(update={
            "estimated_selling_price_tnd": selling_price,
            "gross_margin_per_unit_before_marketing_tnd": None,
            "estimated_margin_per_unit_tnd": None,
            "gross_profit_for_1000_before_marketing_tnd": None,
            "net_profit_for_1000_after_marketing_tnd": None,
            "estimated_profit_for_1000_units_tnd": None,
            "pricing_basis": pricing_basis,
        })
    margin = round(selling_price - landed_cost, 2)
    gross_profit = round(margin * ANALYSIS_QUANTITY_UNITS, 2)
    budget = profitability.digital_ad_budget_default_tnd or DIGITAL_AD_BUDGET_DEFAULT_TND
    return profitability.model_copy(update={
        "estimated_selling_price_tnd": selling_price,
        "pricing_basis": pricing_basis,
        "gross_margin_per_unit_before_marketing_tnd": margin,
        "estimated_margin_per_unit_tnd": margin,
        "gross_profit_for_1000_before_marketing_tnd": gross_profit,
        "net_profit_for_1000_after_marketing_tnd": round(gross_profit - budget, 2),
        "estimated_profit_for_1000_units_tnd": round(gross_profit - budget, 2),
    })


def _canonical_supplier_price(
    validated: ProviderAnalysisResult,
    cost_config: CostConfig,
    product: ProductUnderstanding | None = None,
) -> float | None:
    offer = _canonical_supplier_offer(validated, product)
    if not offer:
        return None
    price_tnd = round(offer.price_min_usd_numeric * cost_config.usd_to_tnd_rate, 2)
    if product is None:
        return price_tnd
    equivalent_price, _ = _supplier_target_package_price(offer, cost_config, product)
    return equivalent_price


def _canonical_supplier_price_range(
    validated: ProviderAnalysisResult,
    cost_config: CostConfig,
    product: ProductUnderstanding | None = None,
) -> tuple[float | None, float | None, ChinaSourcingOffer | None]:
    offer = _canonical_supplier_offer(validated, product)
    if not offer:
        return None, None, None
    if offer.price_min_usd_numeric is None and offer.price_max_usd_numeric is None:
        return None, None, offer
    rate = float(cost_config.usd_to_tnd_rate or 0)
    if rate <= 0:
        return None, None, offer
    minimum_usd = offer.price_min_usd_numeric or offer.price_max_usd_numeric
    maximum_usd = offer.price_max_usd_numeric or minimum_usd
    if minimum_usd is None or maximum_usd is None:
        return None, None, offer
    minimum = round(minimum_usd * rate, 2)
    maximum = round(maximum_usd * rate, 2)
    if product is not None:
        minimum_target, _ = _supplier_target_package_price(offer.model_copy(update={"price_min_usd_numeric": minimum_usd}), cost_config, product)
        maximum_target, _ = _supplier_target_package_price(offer.model_copy(update={"price_min_usd_numeric": maximum_usd}), cost_config, product)
        if minimum_target is None or maximum_target is None:
            return None, None, offer
        minimum, maximum = minimum_target, maximum_target
    return min(minimum, maximum), max(minimum, maximum), offer


def _product_target_volume(product: ProductUnderstanding) -> tuple[float | None, str | None]:
    product_text = " ".join([
        product.original_product,
        product.normalized_product,
        *product.technical_specs,
    ])
    quantity, unit = _parse_volume(product_text)
    return _base_volume(quantity, unit), _base_unit(unit)


def _supplier_price_unit_kind(price_unit: str | None) -> str | None:
    normalized = re.sub(r"\s+", " ", (price_unit or "").lower()).strip()
    if re.search(r"(?:per|/|@)\s*\d+(?:[.,]\d+)?\s*(?:l|litre?s?|liter?s?)\b", normalized):
        return "unit"
    if re.search(r"(?:liter|litre|litres|liters|per l|/l|\bl\b)", normalized):
        return "liter"
    if re.search(r"(?:unit|piece|pcs|bidon|bottle)", normalized):
        return "unit"
    if re.fullmatch(r"\d+(?:[.,]\d+)?\s*(?:l|litre?s?|liter?s?)", normalized):
        return "unit"
    return None


def _canonical_supplier_offer(
    validated: ProviderAnalysisResult,
    product: ProductUnderstanding | None = None,
):
    offers = [
        offer for offer in validated.china_sourcing_offers
        if offer.price_min_usd_numeric is not None
        and offer.source_url
        and offer.name.strip()
        and offer.product_title
        and offer.product_match in {"exact", "close", "broad"}
    ]
    if product is not None:
        offers = [
            offer for offer in offers
            if _supplier_target_package_price(offer, CostConfig(), product)[0] is not None
        ]
    exact = [offer for offer in offers if offer.product_match == "exact"] or offers
    reliable = [offer for offer in exact if offer.confidence in {"high", "medium"}] or exact
    return min(reliable, key=lambda offer: offer.price_min_usd_numeric) if reliable else None


def _has_equivalent_or_weak_china_sourcing(validated: ProviderAnalysisResult) -> bool:
    return any(
        offer.product_match in {"broad", "weak"}
        or "equivalent" in offer.match_notes.lower()
        or "oem" in offer.match_notes.lower()
        for offer in validated.china_sourcing_offers
    )


def _sources_for_offer(url: str, evidence: ProviderEvidence) -> list[ProviderRawSource]:
    exact_matches = [source for source in evidence.sources if source.url == url]
    if exact_matches:
        return exact_matches[:3]
    host = _hostname(url)
    if not host:
        return []
    return [
        source
        for source in evidence.sources
        if source.region_hint == "china_sourcing" and _hostname(source.url) == host
    ][:3]


def _hostname(url: str) -> str:
    return url.split("//", 1)[-1].split("/", 1)[0].lower()


def _evidence_risks(validated: ProviderAnalysisResult) -> list[str]:
    risks: list[str] = []
    for offer in validated.china_sourcing_offers:
        notes = offer.match_notes.strip()
        if offer.product_match in {"broad", "weak"} or "equivalent" in notes.lower() or "oem" in notes.lower():
            risks.append(
                notes
                or "Equivalent OEM or weak China sourcing evidence may not match the exact branded product."
            )
    if _overall_confidence(validated) == "low":
        risks.append("Evidence confidence is low.")
    return risks


def _retail_evidence_debug(evidence: ProviderEvidence, validated: ProviderAnalysisResult) -> dict:
    retail_sources = [
        source for source in evidence.sources
        if source.region_hint in {"tunisia_retail", "tunisia"}
    ]
    known_domains = sorted(
        {
            domain
            for source in retail_sources
            for domain in (
                "mytek.tn",
                "tunisianet.com.tn",
                "spacenet.tn",
                "wikishop.tn",
                "shopiwell.tn",
                "keyshop-tn.com",
                "tayara.tn",
                "affariyet.com",
            )
            if domain in source.url.lower()
        }
    )
    after_cap = len(validated.tunisia_retail_market.retail_offers)
    return {
        "retail_candidate_sources_before_cap": len(retail_sources),
        "retail_candidate_sources_after_cap": after_cap,
        "dropped_retail_sources": max(0, len(retail_sources) - after_cap),
        "known_tunisian_retail_domains_found": known_domains,
    }


def _product_image_debug(evidence: ProviderEvidence, response: PrototypeAnalyzeResponse) -> dict:
    candidates = [
        image_url
        for source in evidence.sources
        for image_url in _source_image_candidates(source)
        if image_url.startswith(("http://", "https://"))
    ]
    return {
        "product_image_candidates_count": len(candidates),
        "product_image_selected_source": response.product_image_source_url,
        "product_image_rejection_reasons": [] if candidates else ["No source-backed image URLs were present in provider evidence."],
    }


def _product_dump(intent: IntentResult) -> dict:
    if intent.product_understanding:
        return intent.product_understanding.model_dump()
    return {}


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))
