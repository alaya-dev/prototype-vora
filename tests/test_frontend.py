from pathlib import Path
import unittest


class FrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = Path("static/index.html").read_text(encoding="utf-8")

    def test_category_selection_is_sent_with_analysis_request(self) -> None:
        self.assertIn('id="categorySelect"', self.html)
        self.assertIn("JSON.stringify({ product, category })", self.html)
        self.assertIn("Agriculture &amp; Food", self.html)
        self.assertIn("Manufacturing &amp; Processing Machinery", self.html)
        self.assertIn("Transportation", self.html)

    def test_evidence_loader_replaces_the_old_pulse(self) -> None:
        self.assertIn('class="loader-wrapper"', self.html)
        self.assertIn("Mapping evidence", self.html)
        self.assertNotIn('class="pulse"', self.html)

    def test_missing_supplier_information_is_described_as_unsourced(self) -> None:
        self.assertIn("Not found in source", self.html)
        self.assertIn("No reliable source-backed suppliers", self.html)

    def test_rate_limit_error_does_not_suggest_missing_keys(self) -> None:
        self.assertIn("Daily Gemini quota exhausted", self.html)
        self.assertIn("Check your Gemini quota or billing", self.html)
