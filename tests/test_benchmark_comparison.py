import unittest

from app.benchmark.comparison import build_comparison_summary
from app.benchmark.schemas import (
    BenchmarkProviderRun,
    ChinaBenchmarkSupplier,
    TunisiaBenchmarkSupplier,
)


class ComparisonSummaryTests(unittest.TestCase):
    def test_summary_is_metric_based(self) -> None:
        runs = [
            BenchmarkProviderRun(
                provider_id="brave",
                provider_name="Brave Search + Gemini",
                status="success",
                latency_ms=200,
                production_risk="medium",
                cost_notes="Medium cost risk.",
                tunisia_cheapest_suppliers=[
                    TunisiaBenchmarkSupplier(
                        name="TN",
                        price_min_tnd_numeric=10,
                        price_evidence="direct",
                        source_url="https://tn.example/1",
                    )
                ],
                china_cheapest_suppliers=[
                    ChinaBenchmarkSupplier(
                        name="CN",
                        price_min_usd_numeric=1,
                        price_evidence="direct",
                        source_url="https://cn.example/1",
                    )
                ],
            ),
            BenchmarkProviderRun(
                provider_id="serper",
                provider_name="Serper + Gemini",
                status="success",
                latency_ms=100,
                production_risk="low",
                cost_notes="Lower cost risk.",
                tunisia_cheapest_suppliers=[
                    TunisiaBenchmarkSupplier(
                        name="TN1",
                        price_min_tnd_numeric=10,
                        price_evidence="direct",
                        source_url="https://tn.example/2",
                    ),
                    TunisiaBenchmarkSupplier(
                        name="TN2",
                        price_min_tnd_numeric=20,
                        price_evidence="direct",
                        source_url="https://tn.example/3",
                    ),
                ],
            ),
        ]

        summary = build_comparison_summary(runs)

        self.assertEqual(summary.fastest_provider, "serper")
        self.assertEqual(summary.most_tunisian_results, "serper")
        self.assertEqual(summary.most_chinese_results, "brave")
        self.assertEqual(summary.lowest_cost_risk, "serper")
        self.assertIn("directional", summary.notes.lower())
        self.assertNotIn("best production provider", summary.notes.lower())
