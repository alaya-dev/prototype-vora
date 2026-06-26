from __future__ import annotations

from app.benchmark.schemas import BenchmarkComparisonSummary, BenchmarkProviderRun


def build_comparison_summary(
    runs: list[BenchmarkProviderRun],
) -> BenchmarkComparisonSummary:
    successful = [run for run in runs if run.status in {"success", "partial"}]
    if not successful:
        return BenchmarkComparisonSummary(
            notes="No successful provider runs were available for comparison."
        )

    risk_rank = {"low": 0, "medium": 1, "high": 2}
    return BenchmarkComparisonSummary(
        fastest_provider=min(successful, key=lambda run: run.latency_ms).provider_id,
        most_tunisian_results=max(
            successful,
            key=lambda run: len(run.tunisia_cheapest_suppliers),
        ).provider_id,
        most_chinese_results=max(
            successful,
            key=lambda run: len(run.china_cheapest_suppliers),
        ).provider_id,
        most_source_backed_prices=max(
            successful,
            key=_source_backed_price_count,
        ).provider_id,
        most_complete_provider=max(
            successful,
            key=_completeness_score,
        ).provider_id,
        lowest_cost_risk=min(
            successful,
            key=lambda run: risk_rank[run.production_risk],
        ).provider_id,
        notes=(
            "Comparison is directional and metric-based; repeat runs across products, "
            "time windows, and provider settings before making production decisions."
        ),
    )


def _source_backed_price_count(run: BenchmarkProviderRun) -> int:
    tunisia_count = sum(
        1
        for supplier in run.tunisia_cheapest_suppliers
        if supplier.price_evidence in {"direct", "snippet"} and supplier.source_url
    )
    china_count = sum(
        1
        for supplier in run.china_cheapest_suppliers
        if supplier.price_evidence in {"direct", "snippet"} and supplier.source_url
    )
    return tunisia_count + china_count


def _completeness_score(run: BenchmarkProviderRun) -> tuple[int, int, int, int]:
    return (
        len(run.tunisia_cheapest_suppliers),
        len(run.china_cheapest_suppliers),
        _source_backed_price_count(run),
        len(run.research_sources),
    )
