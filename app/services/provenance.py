from __future__ import annotations

from app.schemas import SupplierOption


def reconcile_supplier_citations(
    suppliers: list[SupplierOption],
    citation_urls: set[str],
) -> list[SupplierOption]:
    normalized_citation_urls = {
        _normalize_url(url)
        for url in citation_urls
        if url
    }
    reconciled_suppliers = []
    for supplier in suppliers:
        if _normalize_url(supplier.source_url) in normalized_citation_urls:
            reconciled_suppliers.append(supplier)
            continue
        reconciled_suppliers.append(
            supplier.model_copy(
                update={
                    "source_url": None,
                    "confidence": "low",
                }
            )
        )
    return reconciled_suppliers


def _normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    return url.rstrip("/").strip()
