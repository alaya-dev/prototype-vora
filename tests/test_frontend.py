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
        self.assertIn("product_image_confidence", self.html)
        self.assertIn("No reliable source-backed product image was found.", self.html)

    def test_analytics_ui_is_present(self) -> None:
        self.assertIn("/api/analytics/runs", self.html)
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

    def test_client_ui_is_mobile_first_and_uses_contact_cards(self) -> None:
        self.assertIn("@media (min-width: 760px)", self.html)
        self.assertIn("decision-bar", self.html)
        self.assertIn("product-card", self.html)
        self.assertIn("summary-card", self.html)
        self.assertIn("report-row", self.html)
        self.assertIn("Email seller", self.html)
        self.assertIn("WhatsApp seller", self.html)
        self.assertIn("Call seller", self.html)
        self.assertIn("seller_contacts", self.html)
        self.assertNotIn("China wholesale/manufacturer product offer links", self.html)
        self.assertIn("China product unit price", self.html)
        self.assertIn("Estimated landed cost per unit", self.html)
        self.assertIn("Estimated Meta campaign budget", self.html)
        self.assertIn("Estimated retail selling price", self.html)
        self.assertIn("Gross margin per unit before marketing", self.html)
        self.assertIn("Gross profit for 1000 before marketing", self.html)
        self.assertIn("Net profit for 1000 units after campaign", self.html)
        self.assertIn("Email:", self.html)
        self.assertIn("Phone:", self.html)
        self.assertIn("WhatsApp:", self.html)
        self.assertIn("Website:", self.html)
        self.assertIn("Contact page:", self.html)
        self.assertIn("contact.email", self.html)
        self.assertIn("contact.phone", self.html)
        self.assertIn("contact.whatsapp", self.html)
        self.assertIn("contact.website", self.html)
        self.assertIn("contact.contact_page_url", self.html)
        self.assertNotIn("Estimated profit for 100 units", self.html)
        self.assertIn("Direct seller contact was not found from public sources. Please contact one of our sourcing agents", self.html)
        self.assertNotIn("Meta ads cost</strong>", self.html)
        self.assertNotIn("Expected units sold from campaign", self.html)
