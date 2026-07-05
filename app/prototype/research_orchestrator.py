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
    CostConfig,
    DecisionScores,
    ExampleRetailPrice,
    HiddenSourcingLinks,
    LocalizedClientAnalysis,
    ProfitabilityEstimate,
    PrototypeAnalyzeRequest,
    PrototypeAnalyzeResponse,
    PrototypeAnalysisDraft,
    PrototypeSourcingLink,
    RetailMarketSummary,
    SourcingSummary,
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
) -> PrototypeAnalyzeResponse:
    if isinstance(draft, PrototypeAnalysisDraft):
        computed = _response_from_validated(run_id, product, validated, evidence, cost_config, quantity_scenarios, warnings)
        draft_retail = _retail_summary_with_fallbacks(_retail_summary_from_validated(validated))
        base = computed.model_copy(
            update={
                **_image_payload(_valid_image_or_none(draft.product_image_url, evidence), evidence, product),
                "product_description": draft.product_description or computed.product_description,
                "localized_analysis": _localized_analysis_with_fallbacks(
                    draft.localized_analysis,
                    draft.product_description or computed.product_description,
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
    china_prices = [offer.price_min_usd_numeric for offer in validated.china_sourcing_offers if offer.price_min_usd_numeric is not None]
    china_tnd = [round(price * cost_config.usd_to_tnd_rate, 2) for price in china_prices]
    tunisia_prices = [offer.price_min_tnd_numeric for offer in validated.tunisia_sourcing_offers if offer.price_min_tnd_numeric is not None]
    source_unit_price = min(china_tnd or tunisia_prices) if (china_tnd or tunisia_prices) else None
    landed_cost, landed_notes, landed_parts = _landed_cost_breakdown(source_unit_price, cost_config)
    ad_allocation, ad_notes = _ad_allocation(cost_config)
    retail = validated.tunisia_retail_market
    selling_price = retail.price_avg_tnd or retail.price_min_tnd
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

    return PrototypeAnalyzeResponse(
        run_id=run_id,
        product_understanding=product,
        **_image_payload(_first_source_image(evidence), evidence, product),
        product_description=validated.market_summary or product.normalized_product,
        localized_analysis=_localized_analysis_with_fallbacks(
            None,
            validated.market_summary or product.normalized_product,
        ),
        sourcing_summary=SourcingSummary(
            china_price_range=_range_text("US$", china_prices),
            china_price_min_tnd_estimate=min(china_tnd) if china_tnd else None,
            china_price_max_tnd_estimate=max(china_tnd) if china_tnd else None,
            china_moq_summary=", ".join([offer.moq for offer in validated.china_sourcing_offers if offer.moq]) or "MOQ not found.",
            tunisia_wholesale_summary=_tunisia_wholesale_summary(validated.tunisia_sourcing_offers),
            tunisia_wholesale_found=bool(validated.tunisia_sourcing_offers),
            evidence_confidence=_overall_confidence(validated),
        ),
        retail_market_summary=_retail_summary_from_validated(validated),
        analysis_quantity_units=ANALYSIS_QUANTITY_UNITS,
        profitability_estimate=ProfitabilityEstimate(
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
                landed_notes,
                ad_notes,
            ],
            risks=list(dict.fromkeys(warnings + _evidence_risks(validated))),
        ),
        recommendation=recommendation,
        recommendation_reason=recommendation_reason,
        decision_scores=decision_scores,
        **_client_decision_fields(decision_context, decision_scores),
        warnings=warnings,
    )


def _localized_analysis_with_fallbacks(
    localized: LocalizedClientAnalysis | None,
    product_description: str,
) -> LocalizedClientAnalysis:
    base = localized or LocalizedClientAnalysis()
    return base.model_copy(
        update={
            "product_description_en": base.product_description_en or product_description,
            "product_description_fr": base.product_description_fr or product_description,
        }
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


def _valid_image_or_none(url: str | None, evidence: ProviderEvidence) -> str | None:
    if not url:
        return _first_source_image(evidence)
    return url if url.startswith(("http://", "https://")) else _first_source_image(evidence)


def _image_payload(url: str | None, evidence: ProviderEvidence, product: ProductUnderstanding) -> dict:
    if url:
        source = _source_for_image(url, evidence)
        return {
            "product_image_url": url,
            "product_image_source_url": source.url if source else None,
            "product_image_confidence": _image_confidence(source, product) if source else "low",
            "product_image_notes": (
                "Source-backed image selected from provider evidence."
                if source
                else "Image URL returned by analysis output."
            ),
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
    domain_visual = _source_domain_visual(evidence, product)
    if domain_visual:
        source, image_url = domain_visual
        return {
            "product_image_url": image_url,
            "product_image_source_url": source.url,
            "product_image_confidence": "fallback",
            "product_image_notes": "No direct product image was captured; using source-domain visual from provider evidence.",
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
        for image_url in _source_image_candidates(source):
            if image_url.startswith(("http://", "https://")):
                return source, image_url
    return None


def _source_for_image(url: str, evidence: ProviderEvidence) -> ProviderRawSource | None:
    for source in evidence.sources:
        if url in _source_image_candidates(source) or url == _source_domain_visual_for_source(source):
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
        if not cleaned.startswith(("http://", "https://")) or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


def _source_domain_visual(evidence: ProviderEvidence, product: ProductUnderstanding) -> tuple[ProviderRawSource, str] | None:
    sorted_sources = sorted(evidence.sources, key=lambda source: _image_source_score(source, product), reverse=True)
    for source in sorted_sources:
        image_url = _source_domain_visual_for_source(source)
        if image_url:
            return source, image_url
    return None


def _source_domain_visual_for_source(source: ProviderRawSource) -> str | None:
    parsed = urlparse(source.url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}/favicon.ico"


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
    configured = cost_config.default_digital_ad_budget_min_tnd
    if configured is None or configured < 50:
        return DIGITAL_AD_BUDGET_MIN_TND
    return float(configured)


def _digital_ad_budget_max(cost_config: CostConfig) -> float:
    configured = cost_config.default_digital_ad_budget_max_tnd
    if configured is None or configured < 50:
        return DIGITAL_AD_BUDGET_MAX_TND
    return float(configured)


def _digital_ad_budget_default(cost_config: CostConfig) -> float:
    configured = cost_config.default_meta_campaign_budget_tnd
    if configured is not None and configured >= _digital_ad_budget_min(cost_config) and configured <= _digital_ad_budget_max(cost_config):
        return float(configured)
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
    return profitability.model_copy(update={"risks": risks})


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
