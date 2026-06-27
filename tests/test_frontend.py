from pathlib import Path
import unittest


class FrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = Path("static/index.html").read_text(encoding="utf-8")

    def test_benchmark_lab_uses_new_endpoints(self) -> None:
        self.assertIn("Search Provider Benchmark Lab", self.html)
        self.assertIn('fetch("/providers"', self.html)
        self.assertIn('fetch("/benchmark/analyze"', self.html)
        self.assertNotIn('fetch("/analyze"', self.html)

    def test_provider_cards_and_usage_metrics_are_rendered(self) -> None:
        self.assertIn("provider_api_calls", self.html)
        self.assertIn("gemini_intent_calls", self.html)
        self.assertIn("gemini_analysis_calls", self.html)
        self.assertIn("raw_queries_count", self.html)
        self.assertIn("production_risk", self.html)
        self.assertIn("cost_notes", self.html)

    def test_raw_evidence_is_expandable(self) -> None:
        self.assertIn("<details", self.html)
        self.assertIn("Raw evidence", self.html)

    def test_run_all_configured_providers_exists(self) -> None:
        self.assertIn("Run all configured providers", self.html)
        self.assertIn("runAllConfigured", self.html)

    def test_market_result_labels_are_product_price_focused(self) -> None:
        self.assertIn("Tunisia local market prices", self.html)
        self.assertIn("China wholesale product prices", self.html)
        self.assertIn("Product offer", self.html)
        self.assertIn("product_match", self.html)
        self.assertIn("match_notes", self.html)
