import unittest


from app.schemas import SupplierOption
from app.services.provenance import enforce_supplier_url_provenance


class SupplierUrlProvenanceTests(unittest.TestCase):
    def test_only_suppliers_with_evidence_backed_urls_are_returned(self) -> None:
        evidence_urls = {"https://trusted.example/product"}
        suppliers = [
            SupplierOption(
                name="Trusted Source",
                type="source",
                product_title="LED strip lights",
                price_range_tnd=None,
                source_url="https://trusted.example/product",
                confidence="high",
                notes="Matched evidence.",
            ),
            SupplierOption(
                name="Missing URL Source",
                type="source",
                product_title="LED strip lights",
                price_range_tnd=None,
                source_url=None,
                confidence="low",
                notes="No URL.",
            ),
            SupplierOption(
                name="Invented URL Source",
                type="source",
                product_title="LED strip lights",
                price_range_tnd=None,
                source_url="https://invented.example/product",
                confidence="high",
                notes="Model hallucinated the URL.",
            ),
        ]

        sanitized_suppliers = enforce_supplier_url_provenance(suppliers, evidence_urls)

        self.assertEqual(len(sanitized_suppliers), 1)
        self.assertEqual(sanitized_suppliers[0].source_url, "https://trusted.example/product")
        self.assertEqual(sanitized_suppliers[0].confidence, "high")
