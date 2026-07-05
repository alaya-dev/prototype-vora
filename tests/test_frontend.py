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
        self.assertIn("China sourcing prices", self.html)
        self.assertIn("Tunisia sourcing prices", self.html)
        self.assertIn("Tunisia retail market", self.html)
        self.assertIn("Product offer", self.html)
        self.assertIn("seller_density", self.html)
        self.assertIn("unique_sellers_count", self.html)
        self.assertIn("product_match", self.html)
        self.assertIn("match_notes", self.html)

    def test_product_understanding_is_visible(self) -> None:
        self.assertIn("Product understanding", self.html)
        self.assertIn("English search name", self.html)
        self.assertIn("French search name", self.html)
        self.assertIn("Specification questions", self.html)

    def test_empty_tunisia_sourcing_has_clean_message(self) -> None:
        self.assertIn(
            "No reliable Tunisian wholesale sourcing offer was found for this product.",
            self.html,
        )

    def test_client_prototype_flow_uses_prototype_endpoints(self) -> None:
        self.assertIn('fetch("/prototype/analyze"', self.html)
        self.assertIn('/prototype/runs/${currentRunId}/reveal', self.html)
        self.assertIn("GO", self.html)
        self.assertIn("NO GO", self.html)
        self.assertIn("No reliable product image found.", self.html)
        self.assertIn("links are hidden until GO", self.html)
        self.assertIn("Export PDF", self.html)
        self.assertIn("window.print()", self.html)
        self.assertIn("Client Analysis", self.html)
        self.assertIn("Analytics", self.html)
        self.assertIn("/logo/sourcia_logo_transparent_clean_cropped.png", self.html)
        self.assertIn("Sourcia product opportunity report", self.html)
        self.assertIn("product_image_confidence", self.html)
        self.assertIn("No reliable source-backed product image was found.", self.html)

    def test_analytics_ui_is_present(self) -> None:
        self.assertIn("/api/analytics/runs", self.html)
        self.assertIn("/api/analytics/runs/${run.run_id}", self.html)
        self.assertIn("/api/analytics/cost-config", self.html)
        self.assertIn("/api/sourcing-agents", self.html)
        self.assertIn("Estimated research cost", self.html)
        self.assertIn("Firecrawl cost per call", self.html)
        self.assertIn("Tavily cost per call", self.html)
        self.assertIn("Delete", self.html)
        self.assertIn("agentsPage", self.html)
        self.assertIn("Contact enrichment", self.html)
        self.assertIn("contacts_found_count", self.html)
        self.assertIn("contacts_with_email_count", self.html)
        self.assertIn("contact_enrichment_estimated_cost", self.html)
        self.assertIn("Was product image found?", self.html)
        self.assertIn("source_unit_price_tnd", self.html)
        self.assertIn("estimated_landed_cost_per_unit_tnd", self.html)
        self.assertIn("estimated_meta_campaign_budget_tnd", self.html)
        self.assertIn("hidden sourcing URLs", self.html)
        self.assertIn("Contact sources", self.html)
        self.assertIn("Email from", self.html)
        self.assertIn("Website from", self.html)

    def test_client_ui_is_mobile_first_and_reveals_product_links(self) -> None:
        self.assertIn("@media (min-width: 760px)", self.html)
        self.assertIn("decision-bar", self.html)
        self.assertIn("product-card", self.html)
        self.assertIn("summary-card", self.html)
        self.assertIn("analysis-copy", self.html)
        self.assertIn("Price analysis", self.html)
        self.assertIn("Market analysis", self.html)
        self.assertIn("Business reading", self.html)
        self.assertIn("China product offer links", self.html)
        self.assertIn("Cheapest source-backed offer first", self.html)
        self.assertIn("data.china_sourcing_links", self.html)
        self.assertNotIn("China seller contacts", self.html)
        self.assertIn("China product unit price", self.html)
        self.assertIn("Estimated landed cost per unit", self.html)
        self.assertIn("Estimated retail selling price", self.html)
        self.assertIn("Estimated profit after campaign", self.html)
        self.assertNotIn("Estimated Meta campaign budget", self.html)
        self.assertNotIn("Gross margin per unit before marketing", self.html)
        self.assertNotIn("Gross profit for 1000 before marketing", self.html)
        self.assertNotIn("Estimated profit for 100 units", self.html)
        self.assertNotIn("Meta ads cost</strong>", self.html)
        self.assertNotIn("Expected units sold from campaign", self.html)

    def test_client_ui_has_bilingual_toggle_and_guaranteed_image_fallback(self) -> None:
        self.assertIn("languageToggle", self.html)
        self.assertIn("language-segment", self.html)
        self.assertIn("language-option", self.html)
        self.assertIn("aria-pressed", self.html)
        self.assertIn("setLanguage(\"en\")", self.html)
        self.assertIn("setLanguage(\"fr\")", self.html)
        self.assertIn("Français", self.html)
        self.assertIn("applyStaticTranslations()", self.html)
        self.assertIn("data-i18n=\"clientEyebrow\"", self.html)
        self.assertIn("data-i18n-placeholder=\"productPlaceholder\"", self.html)
        self.assertIn("Rapport d'opportunité produit Sourcia", self.html)
        self.assertIn("Analyser le produit", self.html)
        self.assertIn("renderProductImage(data)", self.html)
        self.assertIn("fallbackProductImage(productLabel)", self.html)

    def test_analytics_is_url_only_and_password_gated_in_ui(self) -> None:
        self.assertNotIn("<aside class=\"sidebar\">", self.html)
        self.assertNotIn("data-page=\"analyticsPage\"", self.html)
        self.assertIn("window.location.pathname === \"/analytics\"", self.html)
        self.assertIn("adminPasswordInput", self.html)
        self.assertIn("x-admin-password", self.html)
        self.assertIn("unlockAnalytics", self.html)
        self.assertIn("sourcia_admin_password", self.html)
