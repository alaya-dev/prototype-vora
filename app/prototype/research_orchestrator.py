from __future__ import annotations

import time
from typing import Iterable

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
    ContactEnrichmentMetrics,
    CostConfig,
    ExampleRetailPrice,
    HiddenSourcingLinks,
    ProfitabilityEstimate,
    PrototypeAnalyzeRequest,
    PrototypeAnalyzeResponse,
    PrototypeAnalysisDraft,
    PrototypeSourcingLink,
    RetailMarketSummary,
    SourcingSummary,
)
from app.prototype.contact_enrichment import ContactEnrichmentAgent, _has_usable_contact
from app.prototype.storage import PrototypeStore
from app.schemas import IntentResult, ProductUnderstanding


EVIDENCE_GROUPS = ("china_sourcing", "tunisia_sourcing", "tunisia_retail")
TUNISIA_WHOLESALE_NOT_FOUND = "No reliable Tunisian wholesale sourcing offer was found for this product."


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
        self.contact_enricher = ContactEnrichmentAgent(contact_providers or providers)
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
        reveal = self.store.get_reveal(run_id)
        if reveal.seller_contacts:
            return reveal
        hidden = self.store.get_hidden_links(run_id)
        china_links = [
            PrototypeSourcingLink.model_validate(link)
            for link in hidden.get("china_sourcing_links", [])
        ]
        started = time.perf_counter()
        enrichment = await self.contact_enricher.enrich(china_links)
        for attempt in enrichment.provider_attempts:
            self.store.log_provider_attempt(
                run_id,
                attempt.provider_id,
                "contact_enrichment",
                attempt.status,
                attempt.api_calls,
                attempt.raw_sources_count,
                attempt.latency_ms,
            )
        if enrichment.provider_api_calls:
            self.store.log_api_usage(run_id, "contact_enrichment", 1)
        usable_contacts = [contact for contact in enrichment.contacts if _has_usable_contact(contact)]
        hidden["seller_contacts"] = [contact.model_dump() for contact in usable_contacts]
        self.store.update_hidden_links(run_id, hidden)
        self.store.update_contact_enrichment_metrics(
            run_id,
            ContactEnrichmentMetrics(
                contacts_found_count=len(usable_contacts),
                contacts_with_email_count=sum(1 for contact in usable_contacts if contact.email),
                contacts_with_whatsapp_count=sum(1 for contact in usable_contacts if contact.whatsapp),
                contact_enrichment_latency=enrichment.latency_ms or _elapsed_ms(started),
                contact_enrichment_status=enrichment.status,
                contact_enrichment_reason="Contact enrichment was triggered by the GO reveal endpoint.",
                contact_cards_rejected_count=enrichment.rejected_count,
                contact_rejection_reasons=enrichment.rejection_reasons,
                usable_contacts_found_count=len(usable_contacts),
            ),
        )
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
    return source.region_hint == "tunisia_retail" or any(signal in text for signal in ("boutique", "achat", "vente", "livraison", "magasin", "jumia", "tayara", "mytek"))


def _looks_retail_or_foreign(source: ProviderRawSource) -> bool:
    text = _source_text(source)
    url = source.url.lower()
    return any(marker in url for marker in (".dz", ".ma", ".fr")) or any(
        signal in text
        for signal in ("algerie", "algérie", "algeria", "maroc", "morocco", "france", "boutique", "panier", "jumia", "mytek", "tayara")
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
        draft_retail = _retail_summary_from_validated(validated)
        base = computed.model_copy(
            update={
                **_image_payload(_valid_image_or_none(draft.product_image_url, evidence), evidence, product),
                "product_description": draft.product_description or computed.product_description,
                "retail_market_summary": draft_retail if validated.tunisia_retail_market.retail_offers else draft.retail_market_summary,
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
    return base.model_copy(
        update={
            "sourcing_summary": sourcing_summary,
            "profitability_estimate": profitability,
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
    gross_profit_1000 = round(gross_margin * 1000, 2) if gross_margin is not None else None
    campaign_budget = cost_config.default_meta_campaign_budget_tnd
    net_profit_1000 = (
        round(gross_profit_1000 - float(campaign_budget), 2)
        if gross_profit_1000 is not None and campaign_budget is not None
        else None
    )
    recommendation, recommendation_reason = _conservative_recommendation(
        "investigate_more",
        gross_margin,
        validated,
        None,
    )

    return PrototypeAnalyzeResponse(
        run_id=run_id,
        product_understanding=product,
        **_image_payload(_first_source_image(evidence), evidence, product),
        product_description=validated.market_summary or product.normalized_product,
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
        profitability_estimate=ProfitabilityEstimate(
            source_unit_price_tnd=source_unit_price,
            estimated_shipping_per_unit_tnd=landed_parts["shipping"],
            estimated_customs_per_unit_tnd=landed_parts["customs"],
            estimated_handling_per_unit_tnd=landed_parts["handling"],
            estimated_misc_per_unit_tnd=landed_parts["misc"],
            estimated_landed_cost_per_unit_tnd=landed_cost,
            landed_cost_breakdown_notes=landed_notes,
            estimated_meta_campaign_budget_tnd=cost_config.default_meta_campaign_budget_tnd,
            expected_units_sold_from_campaign=cost_config.default_expected_units_sold_from_campaign,
            estimated_ad_cost_per_sold_unit_tnd=ad_allocation,
            ad_cost_notes=ad_notes,
            estimated_source_cost_tnd=landed_cost,
            estimated_selling_price_tnd=selling_price,
            estimated_meta_ads_cost_per_sale_tnd=ad_allocation,
            gross_margin_per_unit_before_marketing_tnd=gross_margin,
            gross_profit_for_1000_before_marketing_tnd=gross_profit_1000,
            net_profit_for_1000_after_marketing_tnd=net_profit_1000,
            estimated_margin_per_unit_tnd=gross_margin,
            estimated_profit_per_unit_tnd=gross_margin,
            estimated_profit_for_100_units_tnd=None,
            estimated_profit_for_1000_units_tnd=net_profit_1000,
            assumptions=[
                "Profitability is an estimate, not a guarantee.",
                f"USD to TND rate assumed at {cost_config.usd_to_tnd_rate}.",
                landed_notes,
                ad_notes,
            ],
            risks=list(dict.fromkeys(warnings + _evidence_risks(validated))),
        ),
        recommendation=recommendation,
        recommendation_reason=recommendation_reason,
        warnings=warnings,
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
    return url if any(url in source.image_urls for source in evidence.sources) else None


def _image_payload(url: str | None, evidence: ProviderEvidence, product: ProductUnderstanding) -> dict:
    if url:
        source = _source_for_image(url, evidence)
        return {
            "product_image_url": url,
            "product_image_source_url": source.url if source else None,
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


def _ad_allocation(cost_config: CostConfig) -> tuple[float | None, str]:
    budget = cost_config.default_meta_campaign_budget_tnd
    expected_units = cost_config.default_expected_units_sold_from_campaign
    if budget is None or expected_units is None or expected_units <= 0:
        if budget is not None:
            return None, f"Meta campaign budget assumed at {budget:g} TND. Per-unit ad allocation is not calculated in this simplified report."
        return None, "Meta ads campaign estimate requires an admin campaign budget assumption."
    allocation = round(float(budget) / float(expected_units), 2)
    return (
        allocation,
        f"Meta campaign allocation: {budget:g} TND / {expected_units:g} expected units sold = {allocation:g} TND per sold unit. This is an assumption, not a guarantee.",
    )


def _first_source_image(evidence: ProviderEvidence) -> str | None:
    selected = _best_source_image(evidence, ProductUnderstanding())
    return selected[1] if selected else None


def _best_source_image(evidence: ProviderEvidence, product: ProductUnderstanding) -> tuple[ProviderRawSource, str] | None:
    sorted_sources = sorted(evidence.sources, key=lambda source: _image_source_score(source, product), reverse=True)
    for source in sorted_sources:
        for image_url in source.image_urls:
            if image_url.startswith(("http://", "https://")):
                return source, image_url
    return None


def _source_for_image(url: str, evidence: ProviderEvidence) -> ProviderRawSource | None:
    for source in evidence.sources:
        if url in source.image_urls:
            return source
    return None


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
    return RetailMarketSummary(
        retail_price_range_tnd=_range_text("", [retail.price_min_tnd, retail.price_max_tnd], suffix=" TND"),
        retail_min_tnd=retail.price_min_tnd,
        retail_max_tnd=retail.price_max_tnd,
        retail_avg_tnd=retail.price_avg_tnd,
        seller_density=retail.seller_density,
        example_retail_prices=[
            ExampleRetailPrice(
                seller_name=offer.seller_name,
                product_title=offer.product_title,
                price_tnd=offer.price_min_tnd_numeric,
                price_range_tnd=offer.price_range_tnd,
                source_url=offer.source_url,
                confidence=offer.confidence,
            )
            for offer in retail.retail_offers[:10]
        ],
        competition_notes=retail.competition_notes,
        availability_notes=retail.availability_notes,
    )


def _tunisia_wholesale_summary(offers: list[TunisiaSourcingOffer]) -> str:
    prices = [offer.price_min_tnd_numeric for offer in offers if offer.price_min_tnd_numeric is not None]
    if not prices:
        return TUNISIA_WHOLESALE_NOT_FOUND
    return f"Tunisian wholesale/importer/distributor evidence was found around {min(prices):g} to {max(prices):g} TND per unit."


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
        return "no_go", "Estimated gross margin is weak or negative based on available source and retail evidence."
    if profitability and profitability.estimated_landed_cost_per_unit_tnd is None:
        return "investigate_more", "Landed cost assumptions are missing, so VORA cannot produce a confident GO recommendation."
    if not validated.tunisia_retail_market.retail_offers:
        return "investigate_more", "Tunisia retail evidence is missing, so the selling-price assumption needs more validation."
    if _has_equivalent_or_weak_china_sourcing(validated):
        return "investigate_more", "China sourcing appears to rely on equivalent OEM or weak evidence, not a fully verified exact product match."
    if gross_margin is None:
        return "investigate_more", "Evidence is incomplete or margin confidence is not strong enough for a clear GO."
    if current == "go" or gross_margin >= 5:
        return "go", "Evidence suggests positive gross margin before marketing, but logistics and ad performance still need confirmation."
    if not validated.tunisia_sourcing_offers:
        return "investigate_more", "China sourcing and Tunisia retail evidence may be useful, but Tunisian wholesale sourcing was not found."
    return "investigate_more", "Evidence is incomplete or margin confidence is not strong enough for a clear GO."


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
                "jumia.com.tn",
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
        for image_url in source.image_urls
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
