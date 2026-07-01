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
        analysis_result = await self._extract_analysis(product, evidence, request.quantity_scenarios)
        self.store.log_api_usage(run_id, "gemini_analysis", 1)
        validated = validate_provider_result(_as_provider_analysis(analysis_result), evidence.sources)
        response = _to_client_response(
            run_id=run_id,
            product=product,
            draft=analysis_result,
            validated=validated,
            evidence=evidence,
            cost_config=self.store.get_cost_config(),
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

    def reveal(self, run_id: str):
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
                self.store.get_cost_config(),
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
        draft_retail = _retail_summary_from_validated(validated)
        base = PrototypeAnalyzeResponse(
            run_id=run_id,
            product_understanding=product,
            product_image_url=_valid_image_or_none(draft.product_image_url, evidence),
            product_description=draft.product_description,
            sourcing_summary=draft.sourcing_summary,
            retail_market_summary=draft_retail if validated.tunisia_retail_market.retail_offers else draft.retail_market_summary,
            profitability_estimate=draft.profitability_estimate,
            recommendation=draft.recommendation,
            recommendation_reason=draft.recommendation_reason,
            warnings=list(dict.fromkeys(warnings + draft.warnings)),
            links_hidden=True,
        )
    else:
        base = _response_from_validated(run_id, product, validated, evidence, cost_config, quantity_scenarios, warnings)

    hidden_links = HiddenSourcingLinks(
        china_sourcing_links=[
            _china_link(offer, cost_config)
            for offer in validated.china_sourcing_offers
            if offer.source_url
        ],
        tunisia_sourcing_links=[
            _tunisia_link(offer)
            for offer in validated.tunisia_sourcing_offers
            if offer.source_url
        ],
    )
    sourcing_summary = base.sourcing_summary
    if not validated.tunisia_sourcing_offers:
        sourcing_summary = sourcing_summary.model_copy(
            update={
                "tunisia_wholesale_found": False,
                "tunisia_wholesale_summary": TUNISIA_WHOLESALE_NOT_FOUND,
            }
        )
    return base.model_copy(
        update={
            "sourcing_summary": sourcing_summary,
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
    source_cost = min(tunisia_prices or china_tnd) if (tunisia_prices or china_tnd) else None
    retail = validated.tunisia_retail_market
    selling_price = retail.price_avg_tnd or retail.price_min_tnd
    profit = None
    if source_cost is not None and selling_price is not None:
        profit = round(
            selling_price
            - source_cost
            - cost_config.default_meta_ads_cost_per_sale_tnd
            - cost_config.default_shipping_per_unit_tnd
            - cost_config.default_misc_cost_per_unit_tnd,
            2,
        )
    recommendation = "investigate_more"
    if profit is not None and profit > 0 and validated.china_sourcing_offers and retail.retail_offers:
        recommendation = "go" if profit >= 5 else "investigate_more"
    if profit is not None and profit <= 0:
        recommendation = "no_go"

    return PrototypeAnalyzeResponse(
        run_id=run_id,
        product_understanding=product,
        product_image_url=_first_source_image(evidence),
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
            estimated_source_cost_tnd=source_cost,
            estimated_selling_price_tnd=selling_price,
            estimated_meta_ads_cost_per_sale_tnd=cost_config.default_meta_ads_cost_per_sale_tnd,
            estimated_profit_per_unit_tnd=profit,
            estimated_profit_for_100_units_tnd=_scenario_profit(profit, 100),
            estimated_profit_for_1000_units_tnd=_scenario_profit(profit, 1000),
            assumptions=[
                "Profitability is an estimate, not a guarantee.",
                f"USD to TND rate assumed at {cost_config.usd_to_tnd_rate}.",
                f"Meta ads cost per sale assumed at {cost_config.default_meta_ads_cost_per_sale_tnd} TND.",
            ],
            risks=list(dict.fromkeys(warnings)),
        ),
        recommendation=recommendation,
        recommendation_reason=_recommendation_reason(recommendation, profit, validated),
        warnings=warnings,
    )


def _china_link(offer: ChinaSourcingOffer, cost_config: CostConfig) -> PrototypeSourcingLink:
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


def _first_source_image(evidence: ProviderEvidence) -> str | None:
    for source in evidence.sources:
        for image_url in source.image_urls:
            if image_url.startswith(("http://", "https://")):
                return image_url
    return None


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


def _scenario_profit(profit: float | None, quantity: int) -> float | None:
    return round(profit * quantity, 2) if profit is not None else None


def _recommendation_reason(recommendation: str, profit: float | None, validated: ProviderAnalysisResult) -> str:
    if recommendation == "go":
        return "Evidence suggests positive unit margin, but logistics and ad performance still need confirmation."
    if recommendation == "no_go":
        return "Estimated margin is weak or negative based on available source and retail evidence."
    if not validated.tunisia_sourcing_offers:
        return "China sourcing and Tunisia retail evidence may be useful, but Tunisian wholesale sourcing was not found."
    return "Evidence is incomplete or margin confidence is not strong enough for a clear GO."


def _product_dump(intent: IntentResult) -> dict:
    if intent.product_understanding:
        return intent.product_understanding.model_dump()
    return {}


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))
