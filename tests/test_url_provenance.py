import unittest


from app.schemas import SupplierOption
from app.services.provenance import reconcile_supplier_citations


class SupplierUrlProvenanceTests(unittest.TestCase):
    def test_cited_supplier_url_is_preserved(self) -> None:
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
        ]

        sanitized_suppliers = reconcile_supplier_citations(suppliers, evidence_urls)

        self.assertEqual(len(sanitized_suppliers), 1)
        self.assertEqual(sanitized_suppliers[0].source_url, "https://trusted.example/product")
        self.assertEqual(sanitized_suppliers[0].confidence, "high")

    def test_uncited_supplier_url_is_cleared_and_confidence_is_low(self) -> None:
        supplier = SupplierOption(
            name="Unverified Source",
            type="source",
            product_title="LED strip lights",
            source_url="https://invented.example/product",
            confidence="high",
            notes="Model supplied a URL without a grounding citation.",
        )

        sanitized = reconcile_supplier_citations(
            [supplier],
            {"https://trusted.example/product"},
        )

        self.assertEqual(len(sanitized), 1)
        self.assertIsNone(sanitized[0].source_url)
        self.assertEqual(sanitized[0].confidence, "low")

    def test_missing_supplier_url_forces_low_confidence(self) -> None:
        supplier = SupplierOption(
            name="URL Missing",
            type="source",
            product_title="LED strip lights",
            source_url=None,
            confidence="medium",
            notes="No source URL was returned.",
        )

        sanitized = reconcile_supplier_citations([supplier], set())

        self.assertEqual(len(sanitized), 1)
        self.assertIsNone(sanitized[0].source_url)
        self.assertEqual(sanitized[0].confidence, "low")
