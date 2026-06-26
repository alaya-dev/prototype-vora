import unittest

from app.benchmark.schemas import (
    BenchmarkResearchSource,
    ChinaBenchmarkSupplier,
    ProviderAnalysisResult,
    ProviderRawSource,
    TunisiaBenchmarkSupplier,
)
from app.benchmark.validation import validate_provider_result


class BenchmarkValidationTests(unittest.TestCase):
    def test_url_deduplication_and_cheapest_three_are_enforced(self) -> None:
        analysis = ProviderAnalysisResult(
            tunisia_cheapest_suppliers=[
                TunisiaBenchmarkSupplier(name="No Price", source_url="https://example.com/no-price"),
                TunisiaBenchmarkSupplier(name="Third", price_min_tnd_numeric=30, price_range_tnd="30 TND", source_url="https://example.com/3", price_evidence="direct", evidence_level="direct", confidence="high"),
                TunisiaBenchmarkSupplier(name="First", price_min_tnd_numeric=10, price_range_tnd="10 TND", source_url="https://example.com/1", price_evidence="direct", evidence_level="direct", confidence="high"),
                TunisiaBenchmarkSupplier(name="Second", price_min_tnd_numeric=20, price_range_tnd="20 TND", source_url="https://example.com/2", price_evidence="direct", evidence_level="direct", confidence="high"),
                TunisiaBenchmarkSupplier(name="Fourth", price_min_tnd_numeric=40, price_range_tnd="40 TND", source_url="https://example.com/4", price_evidence="direct", evidence_level="direct", confidence="high"),
            ],
            china_cheapest_suppliers=[
                ChinaBenchmarkSupplier(name="C3", price_min_usd_numeric=3, price_range_usd="US$3", source_url="https://china.example/3", price_evidence="direct", moq_evidence="not_found", evidence_level="direct", confidence="high"),
                ChinaBenchmarkSupplier(name="C1", price_min_usd_numeric=1, price_range_usd="US$1", source_url="https://china.example/1", price_evidence="direct", moq_evidence="not_found", evidence_level="direct", confidence="high"),
                ChinaBenchmarkSupplier(name="C2", price_min_usd_numeric=2, price_range_usd="US$2", source_url="https://china.example/2", price_evidence="direct", moq_evidence="not_found", evidence_level="direct", confidence="high"),
                ChinaBenchmarkSupplier(name="C4", price_min_usd_numeric=4, price_range_usd="US$4", source_url="https://china.example/4", price_evidence="direct", moq_evidence="not_found", evidence_level="direct", confidence="high"),
            ],
            research_sources=[
                BenchmarkResearchSource(title="One", url="https://example.com/1", source_type="product_page"),
                BenchmarkResearchSource(title="Duplicate", url="https://example.com/1", source_type="product_page"),
            ],
        )

        validated = validate_provider_result(analysis, raw_sources=[])

        self.assertEqual([supplier.name for supplier in validated.tunisia_cheapest_suppliers], ["First", "Second", "Third"])
        self.assertEqual([supplier.name for supplier in validated.china_cheapest_suppliers], ["C1", "C2", "C3"])
        self.assertEqual(len(validated.research_sources), 1)

    def test_weak_evidence_is_downgraded(self) -> None:
        analysis = ProviderAnalysisResult(
            tunisia_cheapest_suppliers=[
                TunisiaBenchmarkSupplier(
                    name="Homepage",
                    price_min_tnd_numeric=100,
                    price_range_tnd="100 TND",
                    source_url="https://seller.example",
                    evidence_level="direct",
                    price_evidence="direct",
                    confidence="high",
                ),
                TunisiaBenchmarkSupplier(
                    name="Search Result",
                    price_min_tnd_numeric=90,
                    price_range_tnd="90 TND",
                    source_url="https://search.example/result",
                    evidence_level="direct",
                    price_evidence="direct",
                    confidence="high",
                ),
                TunisiaBenchmarkSupplier(
                    name="Missing Price",
                    source_url="https://seller.example/product",
                    evidence_level="direct",
                    price_evidence="direct",
                    confidence="high",
                ),
            ]
        )
        raw_sources = [
            ProviderRawSource(url="https://search.example/result", source_type="search_result"),
            ProviderRawSource(url="https://seller.example/product", source_type="product_page"),
        ]

        validated = validate_provider_result(analysis, raw_sources=raw_sources)
        by_name = {supplier.name: supplier for supplier in validated.tunisia_cheapest_suppliers}

        self.assertEqual(by_name["Homepage"].evidence_level, "weak")
        self.assertEqual(by_name["Homepage"].confidence, "low")
        self.assertEqual(by_name["Search Result"].confidence, "medium")
        self.assertEqual(by_name["Missing Price"].price_evidence, "not_found")
        self.assertEqual(by_name["Missing Price"].price_min_tnd_numeric, None)

    def test_high_confidence_requires_direct_evidence_and_moq_is_normalized(self) -> None:
        analysis = ProviderAnalysisResult(
            china_cheapest_suppliers=[
                ChinaBenchmarkSupplier(
                    name="Indirect",
                    price_min_usd_numeric=5,
                    price_range_usd="US$5",
                    moq=None,
                    source_url="https://supplier.example/item",
                    evidence_level="indirect",
                    price_evidence="snippet",
                    moq_evidence="direct",
                    confidence="high",
                )
            ]
        )

        validated = validate_provider_result(analysis, raw_sources=[])
        supplier = validated.china_cheapest_suppliers[0]

        self.assertEqual(supplier.confidence, "medium")
        self.assertEqual(supplier.moq_evidence, "not_found")
        self.assertIsNone(supplier.moq_numeric)
