from __future__ import annotations

from typing import TypeVar
from urllib.parse import parse_qsl, urlencode, urlparse

from app.benchmark.schemas import (
    BenchmarkResearchSource,
    ChinaBenchmarkSupplier,
    ProviderAnalysisResult,
    ProviderRawSource,
    TunisiaBenchmarkSupplier,
)


SupplierT = TypeVar("SupplierT", TunisiaBenchmarkSupplier, ChinaBenchmarkSupplier)
TRACKING_QUERY_PARAMS = {"gclid", "fbclid"}
EVIDENCE_STRENGTH = {"weak": 0, "indirect": 1, "direct": 2}
CONFIDENCE_STRENGTH = {"low": 0, "medium": 1, "high": 2}


def validate_provider_result(
    analysis: ProviderAnalysisResult,
    raw_sources: list[ProviderRawSource],
) -> ProviderAnalysisResult:
    raw_source_types = {
        _normalize_url(source.url): source.source_type
        for source in raw_sources
        if _is_valid_url(source.url)
    }
    warnings = list(analysis.warnings)
    tunisia = _rank_tunisia(
        [
            _validate_tunisia_supplier(supplier, raw_source_types)
            for supplier in _dedupe_suppliers_by_url(analysis.tunisia_cheapest_suppliers)
            if _supplier_has_valid_or_empty_url(supplier.source_url)
        ]
    )
    china = _rank_china(
        [
            _validate_china_supplier(supplier, raw_source_types)
            for supplier in _dedupe_suppliers_by_url(analysis.china_cheapest_suppliers)
            if _supplier_has_valid_or_empty_url(supplier.source_url)
        ]
    )
    if sum(1 for supplier in tunisia if supplier.price_min_tnd_numeric is not None) < 3:
        warnings.append("Fewer than 3 validated Tunisia price-backed supplier/source results were found.")
    if sum(1 for supplier in china if supplier.price_min_usd_numeric is not None) < 3:
        warnings.append("Fewer than 3 validated China price-backed supplier/source results were found.")

    return analysis.model_copy(
        update={
            "tunisia_cheapest_suppliers": [
                supplier.model_copy(update={"rank": index + 1})
                for index, supplier in enumerate(tunisia[:3])
            ],
            "china_cheapest_suppliers": [
                supplier.model_copy(update={"rank": index + 1})
                for index, supplier in enumerate(china[:3])
            ],
            "research_sources": _dedupe_sources(analysis.research_sources),
            "warnings": list(dict.fromkeys(warnings)),
        }
    )


def _validate_tunisia_supplier(
    supplier: TunisiaBenchmarkSupplier,
    raw_source_types: dict[str | None, str],
) -> TunisiaBenchmarkSupplier:
    update: dict[str, str | float | None] = {}
    normalized_url = _normalize_url(supplier.source_url)
    if supplier.price_min_tnd_numeric is None:
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
    return supplier.model_copy(update=update)


def _validate_china_supplier(
    supplier: ChinaBenchmarkSupplier,
    raw_source_types: dict[str | None, str],
) -> ChinaBenchmarkSupplier:
    update: dict[str, str | float | None] = {}
    normalized_url = _normalize_url(supplier.source_url)
    if supplier.price_min_usd_numeric is None:
        update["price_evidence"] = "not_found"
        update["price_range_usd"] = supplier.price_range_usd
    if supplier.moq is None or supplier.moq_numeric is None:
        update["moq_evidence"] = "not_found"
        update["moq_numeric"] = None
    update.update(
        _evidence_downgrades(
            supplier.source_url,
            supplier.evidence_level,
            supplier.confidence,
            raw_source_types.get(normalized_url),
        )
    )
    return supplier.model_copy(update=update)


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


def _rank_tunisia(suppliers: list[TunisiaBenchmarkSupplier]) -> list[TunisiaBenchmarkSupplier]:
    return sorted(
        suppliers,
        key=lambda supplier: (
            supplier.price_min_tnd_numeric is None,
            supplier.price_min_tnd_numeric if supplier.price_min_tnd_numeric is not None else float("inf"),
        ),
    )


def _rank_china(suppliers: list[ChinaBenchmarkSupplier]) -> list[ChinaBenchmarkSupplier]:
    return sorted(
        suppliers,
        key=lambda supplier: (
            supplier.price_min_usd_numeric is None,
            supplier.price_min_usd_numeric if supplier.price_min_usd_numeric is not None else float("inf"),
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
    if isinstance(supplier, TunisiaBenchmarkSupplier):
        return supplier.price_min_tnd_numeric
    return supplier.price_min_usd_numeric


def _is_tracking_query_param(key: str) -> bool:
    lowered = key.lower()
    return lowered.startswith("utm_") or lowered in TRACKING_QUERY_PARAMS
