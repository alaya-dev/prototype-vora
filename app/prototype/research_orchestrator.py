from __future__ import annotations

from dataclasses import dataclass
import re
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
TUNISIA_WHOLESALE_NOT_FOUND = "No reliable Tunisian wholesale sourcing offer was found for this product."
ANALYSIS_QUANTITY_UNITS = 1000
DIGITAL_AD_BUDGET_MIN_TND = 300.0
DIGITAL_AD_BUDGET_MAX_TND = 500.0
DIGITAL_AD_BUDGET_DEFAULT_TND = 400.0
IMAGE_MARKDOWN_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)", re.IGNORECASE)
IMAGE_HTML_RE = re.compile(r"""<img[^>]+src=["'](https?://[^"']+)["']""", re.IGNORECASE)
META_IMAGE_RE = re.compile(r"""(?:og:image|twitter:image)[^"'=:\n\r>]*[:=]\s*["']?(https?://[^"'\s>]+)""", re.IGNORECASE)
IMAGE_URL_RE = re.compile(r"""https?://[^\s"'()<>]+\.(?:png|jpe?g|webp|gif|svg)(?:\?[^\s"'()<>]*)?""", re.IGNORECASE)


@dataclass(frozen=True)
class DecisionScoreContext:
    model_recommendation: str
    final_recommendation: str
    recommendation_reason: str
    gross_margin: float | None
    validated: ProviderAnalysisResult
    profitability: ProfitabilityEstimate | None


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
        intent = await self.intent_client.classify(product_input)
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
                target_market=request.target_market,
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
        evidence, warnings = await self._collect_evidence(run_id, product)
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
        analysis_result = await self._extract_analysis(product, evidence, request.quantity_scenarios)
        self.store.log_api_usage(run_id, "gemini_analysis", 1)
        validated = validate_provider_result(_as_provider_analysis(analysis_result), evidence.sources)
        response = _to_client_response(
            run_id=run_id,
            product=product,
            draft=analysis_result,
            validated=validated,
            evidence=evidence,
            cost_config=self.cost_config,
            quantity_scenarios=request.quantity_scenarios,
            warnings=list(dict.fromkeys(intent.warnings + warnings + validated.warnings)),
            target_market=request.target_market,
            sourcing_country=request.sourcing_country,
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
            provider_id = getattr(provider, "provider_id", "unknown")
            started = time.perf_counter()
            try:
                evidence = await provider.search_group(product, "tunisia_retail")
                collected.extend(evidence.sources)
                raw_queries += evidence.raw_queries_count
                api_calls += evidence.provider_api_calls
                self.store.log_provider_attempt(
                    run_id,
                    provider_id,
                    "image_discovery",
                    "success",
                    evidence.provider_api_calls,
                    len(evidence.sources),
                    _elapsed_ms(started),
                )
                if _best_source_image(evidence, product):
                    break
            except (ProviderNotConfiguredError, ProviderAdapterError):
                self.store.log_provider_attempt(
                    run_id,
                    provider_id,
                    "image_discovery",
                    "failed",
                    0,
                    0,
                    _elapsed_ms(started),
                )
                continue
        return ProviderEvidence(
            provider_id="prototype_image_discovery",
            sources=_dedupe_sources(collected),
            raw_queries_count=raw_queries,
            provider_api_calls=api_calls,
        )

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
        draft_retail = _retail_summary_with_fallbacks(_retail_summary_from_validated(validated))
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
                    draft.recommendation,
                    draft.recommendation_reason,
                ),
                "retail_market_summary": (
                    draft_retail
                    if validated.tunisia_retail_market.retail_offers
                    else _retail_summary_with_fallbacks(draft.retail_market_summary)
                ),
                "recommendation": draft.recommendation,
                "recommendation_reason": draft.recommendation_reason,
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
    recommendation, recommendation_reason = _conservative_recommendation(
        base.recommendation,
        profitability.gross_margin_per_unit_before_marketing_tnd,
        validated,
        profitability,
    )
    decision_scores = _decision_scores(
        DecisionScoreContext(
            model_recommendation=base.recommendation,
            final_recommendation=recommendation,
            recommendation_reason=recommendation_reason,
            gross_margin=profitability.gross_margin_per_unit_before_marketing_tnd,
            validated=validated,
            profitability=profitability,
        )
    )
    decision_fields = _client_decision_fields(
        DecisionScoreContext(
            model_recommendation=base.recommendation,
            final_recommendation=recommendation,
            recommendation_reason=recommendation_reason,
            gross_margin=profitability.gross_margin_per_unit_before_marketing_tnd,
            validated=validated,
            profitability=profitability,
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
    china_prices = _china_price_points(validated.china_sourcing_offers)
    china_tnd = [round(price * cost_config.usd_to_tnd_rate, 2) for price in china_prices]
    source_unit_price, selling_price, pricing_basis = _comparable_prices(validated, cost_config)
    landed_cost, landed_notes, landed_parts = _landed_cost_breakdown(source_unit_price, cost_config)
    ad_allocation, ad_notes = _ad_allocation(cost_config)
    gross_margin = None
    if landed_cost is not None and selling_price is not None:
        gross_margin = round(selling_price - landed_cost, 2)
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
    recommendation, recommendation_reason = _conservative_recommendation(
        "investigate_more",
        gross_margin,
        validated,
        None,
    )
    decision_context = DecisionScoreContext(
        model_recommendation="investigate_more",
        final_recommendation=recommendation,
        recommendation_reason=recommendation_reason,
        gross_margin=gross_margin,
        validated=validated,
        profitability=None,
    )
    decision_scores = _decision_scores(decision_context)
    sourcing_summary = SourcingSummary(
        china_price_range=_range_text("US$", china_prices),
        china_price_min_tnd_estimate=min(china_tnd) if china_tnd else None,
        china_price_max_tnd_estimate=max(china_tnd) if china_tnd else None,
        china_moq_summary=", ".join([offer.moq for offer in validated.china_sourcing_offers if offer.moq]) or "MOQ not found.",
        tunisia_wholesale_summary=_tunisia_wholesale_summary(validated.tunisia_sourcing_offers),
        tunisia_wholesale_found=bool(validated.tunisia_sourcing_offers),
        evidence_confidence=_overall_confidence(validated),
    )
    retail_summary = _retail_summary_from_validated(validated)
    profitability_estimate = ProfitabilityEstimate(
        source_unit_price_tnd=source_unit_price,
        estimated_shipping_per_unit_tnd=landed_parts["shipping"],
        estimated_customs_per_unit_tnd=landed_parts["customs"],
        estimated_handling_per_unit_tnd=landed_parts["handling"],
        estimated_misc_per_unit_tnd=landed_parts["misc"],
        estimated_landed_cost_per_unit_tnd=landed_cost,
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
        pricing_basis=pricing_basis,
        estimated_meta_ads_cost_per_sale_tnd=ad_allocation,
        gross_margin_per_unit_before_marketing_tnd=gross_margin,
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
) -> tuple[float | None, float | None, str]:
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
        f"{seller_count} référence(s) retail en Tunisie."
    ).strip()
    return LocalizedClientAnalysis(
        product_description_en=product_description_en,
        product_description_fr=product_description_fr,
        price_analysis_en=_fallback_price_analysis_en(product_name, sourcing_summary, retail_summary, profitability),
        price_analysis_fr=_fallback_price_analysis_fr(product_name, sourcing_summary, retail_summary, profitability),
        market_analysis_en=_fallback_market_analysis_en(product_name, retail_summary, validated),
        market_analysis_fr=_fallback_market_analysis_fr(product_name, retail_summary, validated),
        business_reading_en=_fallback_business_reading_en(product_name, profitability, recommendation, recommendation_reason),
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
        f"Les références retail en Tunisie se situent autour de {retail_summary.retail_price_range_tnd}"
        if retail_summary.retail_price_range_tnd
        else "Les prix retail en Tunisie restent trop peu visibles"
    )
    landed_text = (
        f"Le coût rendu estimé est de {profitability.estimated_landed_cost_per_unit_tnd:g} TND/unité avant publicité."
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
            f"Pour {product_name}, la vue retail Tunisie inclut actuellement {seller_count} référence(s) vendeur, "
            f"ce qui suggère une densité visible {density}. {competition} {availability}"
        )
    return (
        f"Pour {product_name}, la validation du marché tunisien reste faible car aucune référence retail avec prix confirmé n'a été trouvée. "
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
        f"La marge brute estimée avant marketing est de {profitability.gross_margin_per_unit_before_marketing_tnd:g} TND/unité"
        if profitability.gross_margin_per_unit_before_marketing_tnd is not None
        else "La marge brute avant marketing ne peut pas encore être confirmée"
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
        if source is None or _image_source_matches_product(source, product):
            return url
    selected = _best_source_image(evidence, product)
    return selected[1] if selected else None


def _image_payload(url: str | None, evidence: ProviderEvidence, product: ProductUnderstanding) -> dict:
    if url and _is_product_image_url(url):
        source = _source_for_image(url, evidence)
        if source is None or _image_source_matches_product(source, product):
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
        f"Source unit price {source_unit_price:g} TND + shipping {shipping:g} TND "
        f"+ customs/import {customs:g} TND + handling {handling:g} TND "
        f"+ misc {misc:g} TND = estimated landed cost {landed:g} TND/unit. "
        "Shipping, customs, handling, and misc values are admin assumptions unless source-backed."
    )
    return landed, note, parts


def _enrichment_fields(
    validated: ProviderAnalysisResult,
    evidence: ProviderEvidence,
    cost_config: CostConfig,
    profitability: ProfitabilityEstimate,
    product: ProductUnderstanding,
) -> dict:
    return {
        "china_offers": _china_offer_views(validated.china_sourcing_offers, cost_config),
        "tunisia_wholesale_offers": _tunisia_wholesale_offer_views(validated.tunisia_sourcing_offers),
        "retail_offers": _retail_offer_views(validated.tunisia_retail_market.retail_offers),
        "landed_cost": _landed_cost_view(profitability),
        "comparability": _comparability_assessment(product, validated),
        "competition_level": _competition_level(validated),
        "detailed_scoring": _detailed_scoring(validated, profitability),
        "commercial_potential_score": _commercial_potential_score(validated),
        "ads_potential_score": _ads_potential_score(validated),
        "sources": _source_references(validated, evidence),
    }


def _china_offer_views(offers: list[ChinaSourcingOffer], cost_config: CostConfig) -> list[SourcingOfferView]:
    views: list[SourcingOfferView] = []
    for offer in offers:
        rate = float(cost_config.usd_to_tnd_rate or 0)
        min_tnd = round(offer.price_min_usd_numeric * rate, 2) if offer.price_min_usd_numeric is not None and rate > 0 else None
        max_tnd = round(offer.price_max_usd_numeric * rate, 2) if offer.price_max_usd_numeric is not None and rate > 0 else None
        views.append(SourcingOfferView(
            name=offer.name,
            supplier_type=offer.type,
            product_title=offer.product_title,
            price_text=offer.price_range_usd,
            price_min=offer.price_min_usd_numeric,
            price_max=offer.price_max_usd_numeric,
            currency="USD" if (offer.price_min_usd_numeric is not None or offer.price_max_usd_numeric is not None or offer.price_range_usd) else "",
            price_min_tnd=min_tnd,
            price_max_tnd=max_tnd,
            moq=offer.moq,
            source_url=offer.source_url,
            confidence=offer.confidence,
            product_match=offer.product_match,
            match_notes=offer.match_notes,
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


def _retail_offer_views(offers: list) -> list[RetailOfferView]:
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
                normalized = round(base_price / liters, 2)
                normalization_note = f"{_format_number(base_price)} TND / {_format_number(volume_quantity)} L = {_format_number(normalized)} TND/L"
            elif kilograms is not None and kilograms > 0:
                normalized = round(base_price / kilograms, 2)
                normalization_note = f"{_format_number(base_price)} TND / {_format_number(volume_quantity)} kg = {_format_number(normalized)} TND/kg"
        if offer.normalized_price_numeric is not None:
            normalized = offer.normalized_price_numeric
            normalization_note = offer.price_normalization_notes or "Normalized price supplied by the research validation layer."
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
        ))
    return views


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


VOLUME_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ml|l\b|ltr|litres?|liters?|kg|kgs|g\b|gr\b|pcs\.?|pieces?|units?|unités?)", re.IGNORECASE)


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
    return f"{value:g}"


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
    return LandedCostView(total_tnd=total, components=components, partial_estimate=partial, note=note)


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


def _competition_level(validated: ProviderAnalysisResult) -> str:
    retail = validated.tunisia_retail_market
    sellers = {offer.seller_name.lower() for offer in retail.retail_offers if offer.seller_name}
    brands = {_extract_brand(offer.product_title or "").lower() for offer in retail.retail_offers}
    brands.discard("")
    signals = len(sellers) + len(brands)
    if not retail.retail_offers:
        return "unknown"
    if signals >= 8:
        return "high"
    if signals >= 4:
        return "medium"
    return "low"


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


def _detailed_scoring(validated: ProviderAnalysisResult, profitability: ProfitabilityEstimate | None) -> DetailedScoring:
    retail = validated.tunisia_retail_market
    unique_sellers = {offer.seller_name.lower() for offer in retail.retail_offers if offer.seller_name}

    demand_score = min(20, len(unique_sellers) * 4 + min(len(retail.retail_offers), 5))
    demand_note = (
        f"{len(unique_sellers)} distinct seller(s) and {len(retail.retail_offers)} retail reference(s) observed."
        if retail.retail_offers
        else "No Tunisia retail evidence observed yet."
    )

    margin_percent = _margin_percent(profitability)
    if margin_percent is None:
        margin_score, margin_note = 0, "Margin could not be computed from current data."
    elif margin_percent >= 30:
        margin_score, margin_note = 20, f"Gross margin is about {margin_percent:.0f}% of selling price."
    elif margin_percent >= 20:
        margin_score, margin_note = 15, f"Gross margin is about {margin_percent:.0f}% of selling price."
    elif margin_percent >= 10:
        margin_score, margin_note = 10, f"Gross margin is about {margin_percent:.0f}% of selling price — thin buffer."
    elif margin_percent > 0:
        margin_score, margin_note = 5, f"Gross margin is only about {margin_percent:.0f}% of selling price."
    else:
        margin_score, margin_note = 0, "Estimated margin is zero or negative."

    confidences = [offer.confidence for offer in validated.china_sourcing_offers]
    if "high" in confidences and len(validated.china_sourcing_offers) >= 2:
        sourcing_score, sourcing_note = 14, f"{len(validated.china_sourcing_offers)} sourcing offer(s) with high-confidence evidence."
    elif "medium" in confidences or validated.china_sourcing_offers:
        sourcing_score, sourcing_note = 9, f"{len(validated.china_sourcing_offers)} sourcing offer(s); logistics cost remains an estimate."
    else:
        sourcing_score, sourcing_note = 3, "No reliable sourcing offer found yet."

    competition_level = _competition_level(validated)
    competition_scores = {"unknown": 7, "low": 14, "medium": 9, "high": 4}
    competition_note = {
        "unknown": "Competition intensity unknown due to missing market evidence.",
        "low": "Few competing sellers/brands observed.",
        "medium": "Moderate number of competing sellers/brands observed.",
        "high": "Many established sellers/brands compete on this product.",
    }[competition_level]

    ads_score = 6 if retail.retail_offers else 3
    ads_note = "Qualitative reading only — no CPC/CPA/ROAS data available."

    recurring = _offers_look_recurring(validated)
    recurrence_score = 8 if recurring else 5
    recurrence_note = (
        "Product looks consumable/recurring based on category signals."
        if recurring else "Repurchase frequency unclear from available evidence."
    )

    differentiation_score = 2
    risks_count = len(_evidence_risks(validated))
    risk_score = max(0, 5 - min(5, risks_count))

    criteria = [
        ScoreCriterion(key="market_demand", score=demand_score, max_score=20, justification=demand_note),
        ScoreCriterion(key="margin", score=margin_score, max_score=20, justification=margin_note),
        ScoreCriterion(key="sourcing", score=sourcing_score, max_score=15, justification=sourcing_note),
        ScoreCriterion(key="competition", score=competition_scores[competition_level], max_score=15, justification=competition_note),
        ScoreCriterion(key="ads_potential", score=ads_score, max_score=10, justification=ads_note),
        ScoreCriterion(key="recurrence", score=recurrence_score, max_score=10, justification=recurrence_note),
        ScoreCriterion(key="differentiation", score=differentiation_score, max_score=5, justification="No clear differentiator evidenced; assume limited differentiation."),
        ScoreCriterion(key="risk", score=risk_score, max_score=5, justification=f"{risks_count} open risk signal(s) from evidence quality."),
    ]
    return DetailedScoring(total=min(100, sum(c.score for c in criteria)), criteria=criteria)


def _commercial_potential_score(validated: ProviderAnalysisResult) -> int:
    scoring = _detailed_scoring(validated, None)
    by_key = {criterion.key: criterion for criterion in scoring.criteria}
    relevant = [by_key[k] for k in ("market_demand", "recurrence", "competition", "differentiation") if k in by_key]
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

    for offer in validated.china_sourcing_offers:
        if offer.source_url:
            add(offer.source_url, "China supplier / price / MOQ")
    for offer in validated.tunisia_sourcing_offers:
        if offer.source_url:
            add(offer.source_url, "Tunisia wholesale price")
    for offer in validated.tunisia_retail_market.retail_offers:
        if offer.source_url:
            add(offer.source_url, "Tunisia retail price")
    for url, source in list(by_url.items()):
        if len(references) >= 24:
            break
        add(url, f"Context evidence ({source.region_hint})")
    return references[:24]


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
    source_text = _source_text(source).lower().replace("-", "")
    product_text = " ".join([
        product.original_product or "",
        product.normalized_product or "",
        " ".join(product.technical_specs or []),
    ]).lower().replace("-", "")
    target_viscosities = re.findall(r"\b\d+w\d+\b", product_text)
    if target_viscosities and not all(viscosity in source_text for viscosity in target_viscosities):
        return False
    if target_viscosities and source.source_type != "product_page":
        return False
    product_terms = {"oil", "huile", "engine", "moteur", "lubricant", "automotive"}
    if any(term in product_text for term in product_terms) and not any(term in source_text for term in product_terms):
        return False
    return True


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
    if min(clean) == max(clean):
        return f"{prefix}{min(clean):g}{suffix}"
    return f"{prefix}{min(clean):g} to {prefix}{max(clean):g}{suffix}"


def _retail_summary_from_validated(validated: ProviderAnalysisResult) -> RetailMarketSummary:
    retail = validated.tunisia_retail_market
    seller_density = _computed_seller_density(retail.retail_offers)
    return _retail_summary_with_fallbacks(RetailMarketSummary(
        retail_price_range_tnd=_range_text("", [retail.price_min_tnd, retail.price_max_tnd], suffix=" TND"),
        retail_min_tnd=retail.price_min_tnd,
        retail_max_tnd=retail.price_max_tnd,
        retail_avg_tnd=retail.price_avg_tnd,
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
            )
            for offer in retail.retail_offers[:10]
        ],
        competition_notes=retail.competition_notes,
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
    return f"Tunisian wholesale/importer/distributor evidence was found around {min(prices):g} to {max(prices):g} TND per unit."


def _digital_ad_budget_min(cost_config: CostConfig) -> float:
    return DIGITAL_AD_BUDGET_MIN_TND


def _digital_ad_budget_max(cost_config: CostConfig) -> float:
    return DIGITAL_AD_BUDGET_MAX_TND


def _digital_ad_budget_default(cost_config: CostConfig) -> float:
    return DIGITAL_AD_BUDGET_DEFAULT_TND


def _overall_confidence(validated: ProviderAnalysisResult) -> str:
    confidences = [
        offer.confidence
        for offer in [*validated.china_sourcing_offers, *validated.tunisia_sourcing_offers]
    ]
    if "high" in confidences:
        return "high"
    if "medium" in confidences:
        return "medium"
    return "low"


def _conservative_recommendation(
    current: str,
    gross_margin: float | None,
    validated: ProviderAnalysisResult,
    profitability: ProfitabilityEstimate | None,
) -> tuple[str, str]:
    if gross_margin is not None and gross_margin <= 0:
        return "no_go", "The opportunity does not currently show an attractive enough margin buffer once sourcing, resale price pressure, and execution risk are considered."
    if profitability and profitability.estimated_landed_cost_per_unit_tnd is None:
        return "investigate_more", "The product shows some commercial potential, but the current cost scenario does not yet leave enough margin buffer for a confident GO."
    if not validated.tunisia_retail_market.retail_offers:
        return "investigate_more", "The opportunity needs more market validation because Tunisia resale price pressure is still not visible enough."
    if _has_equivalent_or_weak_china_sourcing(validated):
        return "investigate_more", "The sourcing side still needs validation because the current supplier evidence is more equivalent-OEM than exact-match."
    if gross_margin is None:
        return "investigate_more", "The product may have potential, but the current evidence does not yet show a margin buffer strong enough for a clear GO."
    if current == "go" or gross_margin >= 5:
        return "go", "The opportunity shows a workable margin buffer and enough price-backed sourcing evidence to move into supplier verification and sample testing."
    if not validated.tunisia_sourcing_offers:
        return "investigate_more", "The opportunity has some traction, but sourcing competitiveness and market positioning still need to be strengthened before a clear GO."
    return "investigate_more", "The opportunity shows some potential, but the current margin buffer is not yet strong enough to justify an immediate GO."


def _decision_scores(context: DecisionScoreContext) -> DecisionScores:
    confidence = _overall_confidence(context.validated)
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
            "The opportunity shows enough price-backed margin buffer to support a cautious GO "
            "and move into supplier verification and sample testing."
        )
    if context.final_recommendation == "no_go":
        return (
            "The risks dominate because the current opportunity does not show enough margin "
            "buffer versus execution risk."
        )
    if scores.go_percent < scores.no_go_percent:
        return (
            "The opportunity shows some potential, but the margin buffer is not yet wide "
            "enough to justify an immediate GO."
        )
    return (
        "The product has positive signals, but the business case is still balanced and "
        "needs stronger validation before scaling."
    )


def _positive_signals(context: DecisionScoreContext) -> list[str]:
    signals: list[str] = []
    retail = context.validated.tunisia_retail_market
    if retail.retail_offers and context.gross_margin is not None and context.gross_margin > 0:
        signals.append("Retail prices appear higher than the estimated source price.")
        signals.append("There may be room for margin before marketing and logistics.")
    elif retail.retail_offers:
        signals.append("Tunisia retail price evidence is available for comparison.")
    if context.validated.china_sourcing_offers:
        signals.append("China sourcing price evidence is available.")
    return signals[:3]


def _risk_signals(context: DecisionScoreContext) -> list[str]:
    signals: list[str] = []
    if not context.validated.tunisia_sourcing_offers:
        signals.append("Local Tunisia wholesale competitiveness is not visible in the evidence.")
    if context.profitability and context.profitability.estimated_landed_cost_per_unit_tnd is None:
        signals.append("The current cost scenario does not yet leave a strong enough safety buffer.")
    if context.gross_margin is None:
        signals.append("The current business case does not yet show a margin buffer strong enough to scale confidently.")
    elif context.gross_margin <= 0:
        signals.append("Estimated margin is weak or negative.")
    elif context.gross_margin < 5:
        signals.append("Estimated margin is thin once campaign and fulfillment pressure are considered.")
    if _has_equivalent_or_weak_china_sourcing(context.validated):
        signals.append("Supplier evidence still relies on equivalent or weak matching.")
    signals.append("Campaign economics still need market validation.")
    return list(dict.fromkeys(signals))[:5]


def _main_decision_factors(context: DecisionScoreContext) -> list[str]:
    factors = [
        "Tunisia retail price range",
        "Landed-cost scenario",
        "Campaign economics",
        "Sourcing competitiveness",
        "Market differentiation",
    ]
    if not context.validated.tunisia_retail_market.retail_offers:
        factors[0] = "Missing Tunisia retail evidence"
    if not context.validated.china_sourcing_offers:
        factors[3] = "Missing China sourcing evidence"
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
    if context.model_recommendation == "no_go":
        return 20
    if context.final_recommendation == "go":
        return 60 if context.model_recommendation != "go" else 65
    return 35 if context.model_recommendation != "go" else 40


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
        factors.append("Estimated landed cost is missing or incomplete.")
    if not context.validated.tunisia_retail_market.retail_offers:
        factors.append("Tunisia retail evidence is missing.")
    if not context.validated.china_sourcing_offers:
        factors.append("China sourcing price evidence is missing.")
    if not context.validated.tunisia_sourcing_offers:
        factors.append(TUNISIA_WHOLESALE_NOT_FOUND)
    if _has_equivalent_or_weak_china_sourcing(context.validated):
        factors.append("China sourcing evidence relies on broad, weak, or equivalent OEM matching.")
    if confidence == "low":
        factors.append("Evidence confidence is low.")
    return factors or [context.recommendation_reason or "Available evidence supports a conservative decision."]


def _margin_decision_factors(gross_margin: float | None) -> list[str]:
    if gross_margin is None:
        return ["Gross margin could not be calculated from source-backed landed cost and retail price."]
    if gross_margin <= 0:
        return ["Estimated gross margin is negative or too close to zero."]
    if gross_margin < 5:
        return ["Estimated gross margin is positive but thin before marketing and logistics variance."]
    return ["Estimated gross margin is positive before marketing."]


def _go_score_reason(context: DecisionScoreContext, confidence: str) -> str:
    if context.gross_margin is not None and context.gross_margin > 0 and confidence in {"medium", "high"}:
        return "Available evidence shows positive estimated gross margin before marketing."
    return "Positive margin and stronger source-backed evidence would support GO."


def _no_go_score_reason(context: DecisionScoreContext, factors: list[str]) -> str:
    if context.recommendation_reason:
        return context.recommendation_reason
    return factors[0] if factors else "Evidence quality or margin is not strong enough for a confident GO."


def _score_explanation(
    context: DecisionScoreContext,
    go_percent: int,
    no_go_percent: int,
    dominant_side: str,
) -> str:
    retail = context.validated.tunisia_retail_market
    profitability = context.profitability
    retail_range = _range_text("", [retail.price_min_tnd, retail.price_max_tnd], suffix=" TND") or "the visible retail range"
    landed_cost = (
        f"{profitability.estimated_landed_cost_per_unit_tnd:g} TND/unit"
        if profitability and profitability.estimated_landed_cost_per_unit_tnd is not None
        else "the current landed-cost scenario"
    )
    margin_text = (
        f"{context.gross_margin:g} TND per unit before marketing"
        if context.gross_margin is not None
        else "the current margin scenario"
    )
    campaign_budget = (
        f"{profitability.estimated_meta_campaign_budget_tnd:g} TND total campaign budget"
        if profitability and profitability.estimated_meta_campaign_budget_tnd is not None
        else "the current campaign economics"
    )
    if dominant_side == "go":
        return (
            f"GO is higher because retail pricing around {retail_range} sits comfortably above {landed_cost}, "
            f"leaving an estimated gross margin of {margin_text}. The sourcing evidence is price-backed enough "
            "to justify supplier verification and sample testing."
        )
    if context.final_recommendation == "no_go":
        return (
            f"NO GO is higher because the opportunity does not currently show a strong enough margin buffer. "
            f"Retail pricing around {retail_range} leaves limited room versus {landed_cost}, while {campaign_budget} "
            "and execution risk reduce the attractiveness of moving forward now."
        )
    if dominant_side == "balanced":
        return (
            f"The score is balanced because the opportunity shows commercial potential, but the margin buffer around "
            f"{margin_text} is not yet wide enough to outweigh sourcing competitiveness and execution risk."
        )
    return (
        f"NO GO is higher because the estimated upside is still modest relative to execution risk. "
        f"Retail pricing around {retail_range} versus {landed_cost} suggests a possible opportunity, but the margin "
        "buffer is not yet strong enough to support an immediate GO."
    )


def _why_go_score(context: DecisionScoreContext, go_percent: int) -> list[str]:
    retail = context.validated.tunisia_retail_market
    profitability = context.profitability
    reasons: list[str] = []
    if profitability and profitability.estimated_selling_price_tnd is not None and profitability.source_unit_price_tnd is not None:
        reasons.append(
            f"Estimated retail selling price is around {profitability.estimated_selling_price_tnd:g} TND versus "
            f"a source product price around {profitability.source_unit_price_tnd:g} TND."
        )
    if context.gross_margin is not None and context.gross_margin > 0:
        reasons.append(
            f"The current scenario leaves an estimated gross margin of {context.gross_margin:g} TND per unit before marketing."
        )
    if retail.retail_offers:
        reasons.append(
            f"{len(retail.retail_offers)} Tunisia retail offer(s) support visible market demand and resale price benchmarking."
        )
    if context.validated.china_sourcing_offers:
        reasons.append(
            f"{len(context.validated.china_sourcing_offers)} China sourcing offer(s) provide price-backed sourcing evidence."
        )
    return reasons[:4] or [f"GO retains {go_percent}% because the market still shows some resale potential."]


def _why_no_go_score(context: DecisionScoreContext, confidence: str) -> list[str]:
    profitability = context.profitability
    reasons: list[str] = []
    if context.gross_margin is None:
        reasons.append("The current margin buffer is not strong enough to support a confident launch decision.")
    elif context.gross_margin <= 0:
        reasons.append(
            f"The estimated gross margin is {context.gross_margin:g} TND per unit before marketing, which is not attractive enough."
        )
    elif context.gross_margin < 5:
        reasons.append(
            f"The estimated gross margin is only {context.gross_margin:g} TND per unit before marketing, leaving limited safety margin."
        )
    if profitability and profitability.estimated_meta_campaign_budget_tnd is not None:
        reasons.append(
            f"The scenario already includes a total digital advertising budget of {profitability.estimated_meta_campaign_budget_tnd:g} TND, which tightens the margin buffer."
        )
    if not context.validated.tunisia_sourcing_offers:
        reasons.append("Local wholesale competitiveness in Tunisia is still not visible in the evidence.")
    if _has_equivalent_or_weak_china_sourcing(context.validated):
        reasons.append("China sourcing relies on equivalent or weak matching, which raises supplier and product-fit risk.")
    if confidence == "low":
        reasons.append("Supplier verification and market differentiation signals are still too soft for an immediate GO.")
    return reasons[:5] or ["Execution risk is still higher than the available upside."]


def _what_would_change_the_decision(context: DecisionScoreContext) -> list[str]:
    actions = [
        f"Confirm supplier terms and a quote for {ANALYSIS_QUANTITY_UNITS} units.",
        "Compare at least two sourcing options to improve price competitiveness.",
        "Validate product quality and exact product fit with a sample.",
        "Pressure-test campaign economics with a small digital advertising test budget.",
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
