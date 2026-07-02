from __future__ import annotations

import re
from typing import TypeVar
from urllib.parse import parse_qsl, urlencode, urlparse

from app.benchmark.schemas import (
    BenchmarkResearchSource,
    ChinaBenchmarkSupplier,
    ChinaSourcingOffer,
    ProviderAnalysisResult,
    ProviderRawSource,
    TunisiaRetailMarket,
    TunisiaRetailOffer,
    TunisiaBenchmarkSupplier,
    TunisiaSourcingOffer,
)


SupplierT = TypeVar("SupplierT", TunisiaBenchmarkSupplier, ChinaBenchmarkSupplier, TunisiaSourcingOffer, ChinaSourcingOffer, TunisiaRetailOffer)
TRACKING_QUERY_PARAMS = {"gclid", "fbclid"}
EVIDENCE_STRENGTH = {"weak": 0, "indirect": 1, "direct": 2}
CONFIDENCE_STRENGTH = {"low": 0, "medium": 1, "high": 2}
PRODUCT_MATCH_GROUP = {"exact": 0, "close": 0, "broad": 1, "weak": 1}
PRODUCT_MATCH_ORDER = {"exact": 0, "close": 1, "broad": 2, "weak": 3}
TND_DECIMAL_RE = re.compile(r"(?<!\d)(\d{1,3}),(\d{3})(?![\d.])")
INTERNATIONAL_DECIMAL_RE = re.compile(r"(?<!\d)(\d{1,3}(?:,\d{3})+)\.(\d{1,2})(?!\d)")
SPACED_THOUSANDS_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[ \u00a0]\d{3})+)(?!\d)")


def validate_provider_result(
    analysis: ProviderAnalysisResult,
    raw_sources: list[ProviderRawSource],
) -> ProviderAnalysisResult:
    raw_source_types = {
        _normalize_url(source.url): source.source_type
        for source in raw_sources
        if _is_valid_url(source.url)
    }
    raw_sources_by_url = {
        _normalize_url(source.url): source
        for source in raw_sources
        if _is_valid_url(source.url)
    }
    warnings = list(analysis.warnings)
    validated_tunisia_sourcing = []
    for offer in _dedupe_suppliers_by_url(analysis.tunisia_sourcing_offers):
        if not _supplier_has_valid_or_empty_url(offer.source_url):
            continue
        validated_offer = _validate_tunisia_sourcing_offer(
            offer,
            raw_source_types,
            raw_sources_by_url,
        )
        if validated_offer is not None:
            validated_tunisia_sourcing.append(validated_offer)
    tunisia_sourcing = _rank_tunisia_sourcing(
        validated_tunisia_sourcing
    )
    china_sourcing = _rank_china(
        [
            _validate_china_offer(offer, raw_source_types)
            for offer in _dedupe_suppliers_by_url(analysis.china_sourcing_offers)
            if _supplier_has_valid_or_empty_url(offer.source_url)
        ]
    )
    retail_market = _validate_tunisia_retail_market(analysis.tunisia_retail_market, raw_source_types)
    tunisia_compat = _rank_tunisia(
        [
            _validate_tunisia_supplier(supplier, raw_source_types)
            for supplier in _dedupe_suppliers_by_url(analysis.tunisia_cheapest_suppliers)
            if _supplier_has_valid_or_empty_url(supplier.source_url)
        ]
    )
    china_compat = _rank_china(
        [
            _validate_china_supplier(supplier, raw_source_types)
            for supplier in _dedupe_suppliers_by_url(analysis.china_cheapest_suppliers)
            if _supplier_has_valid_or_empty_url(supplier.source_url)
        ]
    )
    if sum(1 for offer in tunisia_sourcing if offer.price_min_tnd_numeric is not None) < 3:
        warnings.append("Fewer than 3 validated Tunisia sourcing price-backed offers were found.")
        warnings.append("Fewer than 3 validated Tunisia price-backed supplier/source results were found.")
    if not tunisia_sourcing:
        warnings.append("No source-backed Tunisian wholesale/importer/distributor/manufacturer offer was found for this product.")
    if sum(1 for offer in china_sourcing if offer.price_min_usd_numeric is not None) < 3:
        warnings.append("Fewer than 3 validated China sourcing price-backed offers were found.")
        warnings.append("Fewer than 3 validated China price-backed supplier/source results were found.")
    if sum(1 for offer in retail_market.retail_offers if offer.price_min_tnd_numeric is not None) == 0:
        warnings.append("No validated Tunisia retail market price-backed offers were found.")
    elif retail_market.unique_sellers_count < 3:
        warnings.append("Retail market coverage may be incomplete.")

    missing_data = analysis.missing_data.model_copy()
    if not tunisia_sourcing:
        missing_data = missing_data.model_copy(
            update={
                "tunisia_sourcing": (
                    "No reliable Tunisian wholesale sourcing price was found. "
                    "Retail prices were kept separate in the Tunisia retail market section."
                )
            }
        )

    return analysis.model_copy(
        update={
            "china_sourcing_offers": [
                offer.model_copy(update={"rank": index + 1})
                for index, offer in enumerate(china_sourcing[:3])
            ],
            "tunisia_sourcing_offers": [
                offer.model_copy(update={"rank": index + 1})
                for index, offer in enumerate(tunisia_sourcing[:3])
            ],
            "tunisia_retail_market": retail_market,
            "tunisia_cheapest_suppliers": [
                supplier.model_copy(update={"rank": index + 1})
                for index, supplier in enumerate(tunisia_compat[:3])
            ],
            "china_cheapest_suppliers": [
                supplier.model_copy(update={"rank": index + 1})
                for index, supplier in enumerate(china_compat[:3])
            ],
            "research_sources": _dedupe_sources(analysis.research_sources),
            "warnings": list(dict.fromkeys(warnings)),
            "missing_data": missing_data,
        }
    )


def _validate_tunisia_supplier(
    supplier: TunisiaBenchmarkSupplier,
    raw_source_types: dict[str | None, str],
) -> TunisiaBenchmarkSupplier:
    update: dict[str, str | float | None] = {}
    update.update(_normalize_tnd_price_update(supplier.price_range_tnd, supplier.price_min_tnd_numeric, supplier.price_max_tnd_numeric))
    normalized_url = _normalize_url(supplier.source_url)
    if update.get("price_min_tnd_numeric", supplier.price_min_tnd_numeric) is None:
        update["price_evidence"] = "not_found"
        update["price_range_tnd"] = supplier.price_range_tnd
    update.update(
        _evidence_downgrades(
            supplier.source_url,
            supplier.evidence_level,
            supplier.confidence,
            raw_source_types.get(normalized_url),
        )
    )
    update.update(_product_match_downgrades(supplier.product_match, update.get("confidence", supplier.confidence)))
    return supplier.model_copy(update=update)


def _validate_china_supplier(
    supplier: ChinaBenchmarkSupplier,
    raw_source_types: dict[str | None, str],
) -> ChinaBenchmarkSupplier:
    return ChinaBenchmarkSupplier.model_validate(
        _validate_china_offer(supplier, raw_source_types).model_dump()
    )


def _validate_china_offer(
    supplier: ChinaSourcingOffer,
    raw_source_types: dict[str | None, str],
) -> ChinaSourcingOffer:
    update: dict[str, str | float | None] = {}
    normalized_url = _normalize_url(supplier.source_url)
    if supplier.price_min_usd_numeric is None:
        update["price_evidence"] = "not_found"
        update["price_range_usd"] = supplier.price_range_usd
    if supplier.moq is None or supplier.moq_numeric is None:
        update["moq_evidence"] = "not_found"
        update["moq_numeric"] = None
    if _is_generic_china_supplier_without_price(supplier, raw_source_types.get(normalized_url)):
        update["evidence_level"] = "weak"
        update["confidence"] = "low"
        update["product_match"] = "weak"
    update.update(
        _evidence_downgrades(
            supplier.source_url,
            update.get("evidence_level", supplier.evidence_level),
            update.get("confidence", supplier.confidence),
            raw_source_types.get(normalized_url),
        )
    )
    update.update(
        _product_match_downgrades(
            update.get("product_match", supplier.product_match),
            update.get("confidence", supplier.confidence),
        )
    )
    return supplier.model_copy(update=update)


def _validate_tunisia_sourcing_offer(
    offer: TunisiaSourcingOffer,
    raw_source_types: dict[str | None, str],
    raw_sources_by_url: dict[str | None, ProviderRawSource],
) -> TunisiaSourcingOffer | None:
    update: dict[str, str | float | None] = {}
    update.update(_normalize_tnd_price_update(offer.price_range_tnd, offer.price_min_tnd_numeric, offer.price_max_tnd_numeric))
    normalized_url = _normalize_url(offer.source_url)
    raw_source = raw_sources_by_url.get(normalized_url)
    if _is_non_tunisian_maghrib_or_foreign_source(offer.source_url, raw_source):
        return None
    if _is_retail_source(offer.source_url, raw_source):
        return None
    if not has_tunisia_sourcing_signal(offer, raw_source):
        return None
    if update.get("price_min_tnd_numeric", offer.price_min_tnd_numeric) is None:
        update["price_evidence"] = "not_found"
        update["price_range_tnd"] = offer.price_range_tnd
    if _is_generic_tunisia_sourcing_without_price(offer, raw_source_types.get(normalized_url)):
        update["evidence_level"] = "weak"
        update["confidence"] = "low"
        update["product_match"] = "weak"
    if _is_retail_fallback_in_sourcing(offer):
        return None
    if _is_french_source_about_tunisia(offer.source_url, raw_source) and offer.confidence == "high":
        update["confidence"] = "medium"
    update.update(
        _evidence_downgrades(
            offer.source_url,
            update.get("evidence_level", offer.evidence_level),
            update.get("confidence", offer.confidence),
            raw_source_types.get(normalized_url),
        )
    )
    update.update(
        _product_match_downgrades(
            update.get("product_match", offer.product_match),
            update.get("confidence", offer.confidence),
        )
    )
    return offer.model_copy(update=update)


def _validate_tunisia_retail_offer(
    offer: TunisiaRetailOffer,
    raw_source_types: dict[str | None, str],
) -> TunisiaRetailOffer:
    update: dict[str, str | float | None] = {}
    update.update(_normalize_tnd_price_update(offer.price_range_tnd, offer.price_min_tnd_numeric, offer.price_max_tnd_numeric))
    normalized_url = _normalize_url(offer.source_url)
    if update.get("price_min_tnd_numeric", offer.price_min_tnd_numeric) is None:
        update["price_evidence"] = "not_found"
        update["price_range_tnd"] = offer.price_range_tnd
    update.update(
        _evidence_downgrades(
            offer.source_url,
            offer.evidence_level,
            offer.confidence,
            raw_source_types.get(normalized_url),
        )
    )
    update.update(_product_match_downgrades(offer.product_match, update.get("confidence", offer.confidence)))
    return offer.model_copy(update=update)


def _validate_tunisia_retail_market(
    market: TunisiaRetailMarket,
    raw_source_types: dict[str | None, str],
) -> TunisiaRetailMarket:
    offers = _rank_tunisia_retail(
        [
            _validate_tunisia_retail_offer(offer, raw_source_types)
            for offer in _dedupe_suppliers_by_url(market.retail_offers)
            if _supplier_has_valid_or_empty_url(offer.source_url)
        ]
    )[:10]
    ranked_offers = [
        offer.model_copy(update={"rank": index + 1})
        for index, offer in enumerate(offers)
    ]
    priced = [
        offer.price_min_tnd_numeric
        for offer in ranked_offers
        if offer.price_min_tnd_numeric is not None
    ]
    unique_sellers = _count_unique_retail_sellers(ranked_offers)
    return market.model_copy(
        update={
            "retail_offers": ranked_offers,
            "price_min_tnd": min(priced) if priced else None,
            "price_max_tnd": max(priced) if priced else None,
            "price_avg_tnd": round(sum(priced) / len(priced), 2) if priced else None,
            "unique_sellers_count": unique_sellers,
            "retail_sources_count": sum(1 for offer in ranked_offers if offer.source_url),
            "seller_density": _seller_density(unique_sellers),
        }
    )


def _evidence_downgrades(
    url: str,
    evidence_level: str,
    confidence: str,
    raw_source_type: str | None,
) -> dict[str, str]:
    update: dict[str, str] = {}
    if _is_homepage_url(url):
        update["evidence_level"] = "weak"
        update["confidence"] = "low"
        return update
    if raw_source_type == "search_result" and confidence == "high":
        update["confidence"] = "medium"
    effective_evidence = update.get("evidence_level", evidence_level)
    effective_confidence = update.get("confidence", confidence)
    if effective_confidence == "high" and effective_evidence != "direct":
        update["confidence"] = "medium"
    return update


def _product_match_downgrades(product_match: str, confidence: str) -> dict[str, str]:
    if product_match == "weak":
        return {"confidence": "low"}
    if product_match == "broad" and confidence == "high":
        return {"confidence": "medium"}
    return {}


def _is_generic_china_supplier_without_price(
    supplier: ChinaSourcingOffer,
    raw_source_type: str | None,
) -> bool:
    generic_source = raw_source_type == "supplier_profile" or supplier.type in {
        "manufacturer",
        "trading_company",
        "supplier_profile",
    }
    return generic_source and supplier.price_min_usd_numeric is None


def _is_generic_tunisia_sourcing_without_price(
    offer: TunisiaSourcingOffer,
    raw_source_type: str | None,
) -> bool:
    generic_source = raw_source_type == "supplier_profile" or offer.type in {
        "wholesaler",
        "importer",
        "distributor",
        "manufacturer",
        "b2b_seller",
    }
    return generic_source and offer.price_min_tnd_numeric is None


def _is_retail_fallback_in_sourcing(offer: TunisiaSourcingOffer) -> bool:
    return offer.type == "marketplace_source"


def _is_tunisian_source(url: str, raw_source: ProviderRawSource | None) -> bool:
    text = _source_text(raw_source)
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    return hostname.endswith(".tn") or "tunisie" in text or "tunisia" in text


def _is_non_tunisian_maghrib_or_foreign_source(
    url: str,
    raw_source: ProviderRawSource | None,
) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    text = _source_text(raw_source)
    if hostname.endswith(".dz") or "algerie" in text or "algérie" in text or "algeria" in text:
        return True
    if hostname.endswith(".ma") or "maroc" in text or "morocco" in text:
        return True
    if hostname.endswith(".fr"):
        return not ("tunisie" in text or "tunisia" in text)
    return False


def _is_french_source_about_tunisia(url: str, raw_source: ProviderRawSource | None) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return hostname.endswith(".fr") and _is_tunisian_source(url, raw_source)


def _is_retail_source(url: str, raw_source: ProviderRawSource | None) -> bool:
    text = _source_text(raw_source)
    hostname = (urlparse(url).hostname or "").lower()
    retail_domains = ("jumia", "mytek", "spacenet", "tayara")
    retail_signals = (
        "boutique",
        "achat",
        "shop",
        "panier",
        "livraison",
        "local store",
        "retail store",
        "magasin",
    )
    return any(domain in hostname for domain in retail_domains) or any(signal in text for signal in retail_signals)


def has_tunisia_sourcing_signal(
    offer: TunisiaSourcingOffer,
    raw_source: ProviderRawSource | None,
) -> bool:
    text = f"{_source_text(raw_source)} {offer.name} {offer.type} {offer.notes}".lower()
    positive_signals = (
        "grossiste",
        "prix gros",
        "vente en gros",
        "fournisseur",
        "distributeur",
        "importateur",
        "fabricant",
        "usine",
        "b2b",
        "prix revendeur",
        "vente par lot",
        "semi gros",
        "wholesaler",
        "distributor",
        "importer",
        "manufacturer",
    )
    return any(signal in text for signal in positive_signals)


def _source_text(raw_source: ProviderRawSource | None) -> str:
    if raw_source is None:
        return ""
    return " ".join(
        part
        for part in (raw_source.title, raw_source.snippet, raw_source.content or "")
        if part
    ).lower()


def _rank_tunisia(suppliers: list[TunisiaBenchmarkSupplier]) -> list[TunisiaBenchmarkSupplier]:
    return sorted(
        suppliers,
        key=lambda supplier: (
            supplier.price_min_tnd_numeric is None,
            supplier.price_min_tnd_numeric if supplier.price_min_tnd_numeric is not None else float("inf"),
        ),
    )


def _rank_tunisia_sourcing(suppliers: list[TunisiaSourcingOffer]) -> list[TunisiaSourcingOffer]:
    return sorted(
        suppliers,
        key=lambda supplier: (
            supplier.price_min_tnd_numeric is None,
            _is_retail_fallback_in_sourcing(supplier),
            PRODUCT_MATCH_GROUP.get(supplier.product_match, 1),
            supplier.price_min_tnd_numeric if supplier.price_min_tnd_numeric is not None else float("inf"),
            PRODUCT_MATCH_ORDER.get(supplier.product_match, 3),
        ),
    )


def _rank_tunisia_retail(offers: list[TunisiaRetailOffer]) -> list[TunisiaRetailOffer]:
    return sorted(
        offers,
        key=lambda offer: (
            offer.price_min_tnd_numeric is None,
            offer.price_min_tnd_numeric if offer.price_min_tnd_numeric is not None else float("inf"),
            PRODUCT_MATCH_ORDER.get(offer.product_match, 3),
        ),
    )


def _rank_china(suppliers: list[ChinaBenchmarkSupplier]) -> list[ChinaBenchmarkSupplier]:
    return sorted(
        suppliers,
        key=lambda supplier: (
            supplier.price_min_usd_numeric is None,
            PRODUCT_MATCH_GROUP.get(supplier.product_match, 1),
            supplier.price_min_usd_numeric if supplier.price_min_usd_numeric is not None else float("inf"),
            PRODUCT_MATCH_ORDER.get(supplier.product_match, 3),
        ),
    )


def _dedupe_suppliers_by_url(suppliers: list[SupplierT]) -> list[SupplierT]:
    deduped_by_url: dict[str, SupplierT] = {}
    unique_without_url: list[SupplierT] = []
    for supplier in suppliers:
        normalized = _normalize_url(supplier.source_url)
        if normalized:
            current = deduped_by_url.get(normalized)
            if current is None or _is_better_supplier(supplier, current):
                deduped_by_url[normalized] = supplier.model_copy(update={"source_url": normalized})
            continue
        unique_without_url.append(supplier)
    return list(deduped_by_url.values()) + unique_without_url


def _dedupe_sources(sources: list[BenchmarkResearchSource]) -> list[BenchmarkResearchSource]:
    seen_urls: set[str] = set()
    unique_sources: list[BenchmarkResearchSource] = []
    for source in sources:
        normalized = _normalize_url(source.url)
        if normalized is None or normalized in seen_urls:
            continue
        seen_urls.add(normalized)
        unique_sources.append(source.model_copy(update={"url": normalized}))
    return unique_sources


def _supplier_has_valid_or_empty_url(url: str) -> bool:
    return not url or _is_valid_url(url)


def _is_valid_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_homepage_url(url: str) -> bool:
    if not _is_valid_url(url):
        return False
    parsed = urlparse(url)
    return parsed.path in {"", "/"}


def _normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_tracking_query_param(key)
    ]
    normalized_path = parsed.path.rstrip("/")
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo = f"{userinfo}:{parsed.password}"
        userinfo = f"{userinfo}@"
    port = f":{parsed.port}" if parsed.port is not None else ""
    normalized_netloc = f"{userinfo}{hostname}{port}"
    return parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=normalized_netloc,
        path=normalized_path,
        query=urlencode(filtered_query, doseq=True),
        fragment="",
    ).geturl()


def _is_better_supplier(candidate: SupplierT, current: SupplierT) -> bool:
    candidate_key = _supplier_quality_key(candidate)
    current_key = _supplier_quality_key(current)
    return candidate_key > current_key


def _supplier_quality_key(supplier: SupplierT) -> tuple[int, float, int, int]:
    numeric_price = _supplier_numeric_price(supplier)
    has_numeric_price = numeric_price is not None
    price_sort_value = -numeric_price if numeric_price is not None else float("-inf")
    return (
        1 if has_numeric_price else 0,
        price_sort_value,
        EVIDENCE_STRENGTH.get(supplier.evidence_level, -1),
        CONFIDENCE_STRENGTH.get(supplier.confidence, -1),
    )


def _supplier_numeric_price(supplier: SupplierT) -> float | None:
    if isinstance(supplier, TunisiaBenchmarkSupplier | TunisiaSourcingOffer | TunisiaRetailOffer):
        return supplier.price_min_tnd_numeric
    return supplier.price_min_usd_numeric


def _count_unique_retail_sellers(offers: list[TunisiaRetailOffer]) -> int:
    unique: set[str] = set()
    for offer in offers:
        seller_name = offer.seller_name.strip().lower()
        if seller_name:
            unique.add(f"name:{seller_name}")
            continue
        normalized_url = _normalize_url(offer.source_url)
        if normalized_url:
            parsed = urlparse(normalized_url)
            if parsed.hostname:
                unique.add(f"domain:{parsed.hostname.lower()}")
    return len(unique)


def _seller_density(unique_sellers: int) -> str:
    if unique_sellers <= 0:
        return "unknown"
    if unique_sellers <= 2:
        return "unknown"
    if unique_sellers <= 5:
        return "medium"
    return "high"


def _normalize_tnd_price_update(
    price_text: str | None,
    price_min: float | None,
    price_max: float | None,
) -> dict[str, str | float | None]:
    if not price_text:
        return {}
    lowered = price_text.lower()
    if "tnd" not in lowered and "dt" not in lowered and "د.ت" not in lowered:
        return {}

    parsed = _parse_tnd_price_text(price_text)
    if parsed is None:
        return {"original_price_text": price_text}

    parsed_min, parsed_max, note = parsed
    current_min = price_min
    current_max = price_max
    should_replace_min = current_min is None or _looks_unrealistic_tnd(current_min, parsed_min)
    should_replace_max = current_max is None or _looks_unrealistic_tnd(current_max, parsed_max)
    if not should_replace_min and not should_replace_max:
        return {"original_price_text": price_text}

    normalized_min = parsed_min if should_replace_min else current_min
    normalized_max = parsed_max if should_replace_max else current_max
    if normalized_max == normalized_min:
        normalized_max = normalized_min
    return {
        "original_price_text": price_text,
        "normalized_price_numeric": normalized_min,
        "price_min_tnd_numeric": normalized_min,
        "price_max_tnd_numeric": normalized_max,
        "price_range_tnd": _format_tnd_range(normalized_min, normalized_max),
        "price_normalization_notes": note,
    }


def _parse_tnd_price_text(price_text: str) -> tuple[float, float, str] | None:
    text = price_text.replace("\u00a0", " ")
    if match := INTERNATIONAL_DECIMAL_RE.search(text):
        value = float(match.group(1).replace(",", "") + "." + match.group(2))
        return value, value, "Parsed international decimal TND price format."
    if match := TND_DECIMAL_RE.search(text):
        whole = match.group(1)
        decimals = match.group(2).rstrip("0")
        value = float(f"{whole}.{decimals}") if decimals else float(whole)
        return value, value, "Tunisian comma decimal format normalized."
    if match := SPACED_THOUSANDS_RE.search(text):
        value = float(match.group(1).replace(" ", ""))
        return value, value, "TND spaced thousands format normalized."

    numeric_match = re.search(r"(?<!\d)(\d+(?:[.]\d{1,2})?)(?!\d)", text)
    if numeric_match:
        value = float(numeric_match.group(1))
        return value, value, "TND numeric price parsed from text."
    return None


def _looks_unrealistic_tnd(current: float, parsed: float) -> bool:
    if current == parsed:
        return False
    if current >= 1000 and parsed < 1000:
        return True
    return current is None


def _format_tnd_range(price_min: float | None, price_max: float | None) -> str | None:
    if price_min is None:
        return None
    if price_max is None or price_max == price_min:
        return f"{price_min:g} TND"
    return f"{price_min:g} to {price_max:g} TND"


def _is_tracking_query_param(key: str) -> bool:
    lowered = key.lower()
    return lowered.startswith("utm_") or lowered in TRACKING_QUERY_PARAMS
