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
        self.assertIn("/logo/Nexora_logo_transparent_clean_cropped.png", self.html)
        self.assertIn("Nexora product opportunity report", self.html)
        self.assertIn("product_image_confidence", self.html)
        self.assertIn("No reliable source-backed product image was found.", self.html)

    def test_analysis_loader_replaces_skeleton_during_client_analysis(self) -> None:
        self.assertIn("analysis-loader", self.html)
        self.assertIn("letter-loader", self.html)
        self.assertIn("loader-letter", self.html)
        self.assertIn("white-space: nowrap", self.html)
        self.assertIn("renderAnalysisPendingState()", self.html)
        self.assertIn("Analyzing", self.html)
        self.assertIn("Analyse en cours", self.html)
        self.assertIn("Analyzing product opportunity", self.html)
        self.assertNotIn("Gener" + "ating", self.html)
        self.assertNotIn('prototypeResult.innerHTML = `<div class="result-band wide loading"><div class="skeleton"', self.html)

    def test_product_image_area_has_search_loader(self) -> None:
        self.assertIn("renderImageLoader()", self.html)
        self.assertIn("evidence-spinner", self.html)
        self.assertIn("Finding product", self.html)
        self.assertIn("Searching evidence", self.html)
        self.assertIn("Recherche du produit", self.html)
        self.assertIn("Recherche de preuves", self.html)
        self.assertIn("@media (max-width: 520px)", self.html)
        self.assertIn("prefers-reduced-motion", self.html)

    def test_css_media_rules_do_not_leak_into_script(self) -> None:
        script = self.html.split("<script>", 1)[1].split("</script>", 1)[0]

        self.assertNotIn("@media", script)
        self.assertNotIn("prefers-reduced-motion", script)

    def test_decision_illustration_and_translation_keys_exist(self) -> None:
        self.assertIn("renderDecisionIllustration(data)", self.html)
        self.assertIn("decision_scores", self.html)
        self.assertIn("decision-meter", self.html)
        self.assertIn("GO score", self.html)
        self.assertIn("NO GO score", self.html)
        self.assertIn("Decision confidence", self.html)
        self.assertIn("Recommendation", self.html)
        self.assertIn("Score explanation", self.html)
        self.assertIn("GO drivers", self.html)
        self.assertIn("NO GO drivers", self.html)
        self.assertIn("What would change the decision", self.html)
        self.assertIn("Main decision factors", self.html)
        self.assertIn("Investigate more", self.html)
        self.assertIn("Score GO", self.html)
        self.assertIn("Score NO GO", self.html)
        self.assertIn("Recommandation", self.html)
        self.assertIn("Explication du score", self.html)
        self.assertIn("Facteurs en faveur du GO", self.html)
        self.assertIn("Facteurs en faveur du NO GO", self.html)

    def test_decision_renderer_does_not_render_repeated_reason_fields(self) -> None:
        decision_renderer = self.html.split("function renderDecisionIllustration(data)", 1)[1].split("function normalizeDecisionScores", 1)[0]

        self.assertNotIn("scores.go_reason", decision_renderer)
        self.assertNotIn("scores.no_go_reason", decision_renderer)
        self.assertIn("decisionScoreExplanation", decision_renderer)
        self.assertIn("decisionGoDrivers", decision_renderer)
        self.assertIn("decisionNoGoDrivers", decision_renderer)

    def test_decision_change_actions_helper_exists(self) -> None:
        self.assertIn("function decisionChangeActions(data, scores, recommendation)", self.html)
        self.assertIn("what_would_change_the_decision", self.html)

    def test_seller_density_is_not_rendered_in_client_ui(self) -> None:
        result_renderer = self.html.split("function renderPrototypeResult(data)", 1)[1].split("function renderAnalysisPendingState", 1)[0]

        self.assertNotIn("seller_density", result_renderer)
        self.assertNotIn("Seller density", self.html)
        self.assertNotIn("Densité vendeurs", self.html)

    def test_favicon_is_referenced_from_logo_folder(self) -> None:
        self.assertIn('<link rel="icon" href="/logo/favicon.ico">', self.html)
        self.assertTrue(Path("logo/favicon.ico").exists())

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
        self.assertIn("Analysis quantity: 1000 units", self.html)
        self.assertIn("Gross margin per unit before advertising", self.html)
        self.assertIn("Gross profit for 1000 units before advertising", self.html)
        self.assertIn("Total digital advertising budget for the scenario", self.html)
        self.assertIn("Net profit for 1000 units after advertising", self.html)
        self.assertNotIn("Estimated profit for 100 units", self.html)
        self.assertNotIn('quantity_scenarios: [100, 1000]', self.html)
        client_html = self.html.split('<section id="clientPage"', 1)[1].split('<section id="analyticsPage"', 1)[0]
        self.assertNotIn("Meta campaign", client_html)
        self.assertNotIn("Meta ads", client_html)

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
        self.assertIn("Rapport d'opportunité produit Nexora", self.html)
        self.assertIn("Analyser le produit", self.html)
        self.assertIn("renderProductImage(data)", self.html)
        self.assertIn("fallbackProductImage(productLabel)", self.html)
        self.assertIn("localizedText(data.localized_analysis", self.html)
        self.assertIn("price_analysis", self.html)
        self.assertIn("market_analysis", self.html)
        self.assertIn("business_reading", self.html)

    def test_analytics_is_url_only_and_password_gated_in_ui(self) -> None:
        self.assertNotIn("<aside class=\"sidebar\">", self.html)
        self.assertNotIn("data-page=\"analyticsPage\"", self.html)
        self.assertIn("window.location.pathname === \"/analytics\"", self.html)
        self.assertIn("adminPasswordInput", self.html)
        self.assertIn("x-admin-password", self.html)
        self.assertIn("unlockAnalytics", self.html)
        self.assertIn("Nexora_admin_password", self.html)

    def test_frontend_has_no_removed_marketplace_reference(self) -> None:
        removed_marketplace = "Ju" + "mia"
        self.assertNotIn(removed_marketplace, self.html)
        self.assertNotIn(removed_marketplace.lower(), self.html)

    def test_sourcing_agent_email_composer_is_present(self) -> None:
        self.assertIn("renderSourcingAgentComposer", self.html)
        self.assertIn("generateSourcingEmail()", self.html)
        self.assertIn("copyGeneratedEmail('body')", self.html)
        self.assertIn("copyGeneratedEmail('subject')", self.html)
        self.assertIn("Open mail client", self.html)
        self.assertIn("renderOpenMailClientButton", self.html)
        self.assertIn("mailto:", self.html)
        self.assertIn("Contact a sourcing agent", self.html)
        self.assertIn("Contacter un agent de sourcing", self.html)

    def test_frontend_formats_retail_intervals_with_en_dash(self) -> None:
        self.assertIn('return `${formatNumber(Number(minValue))}–${formatNumber(Number(maxValue))} TND`;', self.html)
        self.assertIn("Category/listing page", self.html)
        self.assertIn("Page catégorie/liste", self.html)

    def test_digital_ad_budget_range_guards_against_legacy_low_values(self) -> None:
        self.assertIn("digital_ad_budget_min_tnd", self.html)
        self.assertIn("digital_ad_budget_max_tnd", self.html)
        self.assertIn("finiteOrNull", self.html)

    def test_frontend_derives_retail_summary_from_examples_when_summary_fields_are_missing(self) -> None:
        self.assertIn("function deriveRetailSummary(retail)", self.html)
        self.assertIn("function retailExampleValues(item)", self.html)
        self.assertIn("const retail = deriveRetailSummary(data.retail_market_summary || {});", self.html)

    def test_frontend_derives_profitability_from_margin_and_1000_unit_scenario(self) -> None:
        self.assertIn("function deriveProfitability(data)", self.html)
        self.assertIn("grossMargin * quantityUnits", self.html)
        self.assertIn("grossProfit - campaignBudget", self.html)
        self.assertIn("const profit = deriveProfitability(data);", self.html)

    def test_report_renderer_keeps_market_tables_separate_and_uses_real_row_variable(self) -> None:
        report = Path("static/report.js").read_text(encoding="utf-8")
        self.assertNotIn("retailRows", report)
        self.assertIn("const wholesaleRows", report)
        self.assertIn("labels.availabilityCol", report)
        self.assertIn("labels.cityCol", report)
        self.assertIn("pricing_basis", report)
        self.assertIn("provenanceText(\"estimate\")", report)
        self.assertNotIn("detailPair(labels.landedCost, landed != null ? `${tnd(landed)} ${provenanceBadge", report)
