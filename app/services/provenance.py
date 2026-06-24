from __future__ import annotations

from app.schemas import SupplierOption


def enforce_supplier_url_provenance(
    suppliers: list[SupplierOption],
    evidence_urls: set[str],
) -> list[SupplierOption]:
    normalized_evidence_urls = {_normalize_url(url) for url in evidence_urls if url}
    return [
        supplier
        for supplier in suppliers
        if _normalize_url(supplier.source_url) in normalized_evidence_urls
    ]


def _normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    return url.rstrip("/").strip()
