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
                TunisiaBenchmarkSupplier(
                    name="Worse Duplicate",
                    price_min_tnd_numeric=50,
                    price_range_tnd="50 TND",
                    source_url="https://EXAMPLE.com/dup?utm_source=ads",
                    price_evidence="snippet",
                    evidence_level="indirect",
                    confidence="medium",
                ),
                TunisiaBenchmarkSupplier(
                    name="Better Duplicate",
                    price_min_tnd_numeric=15,
                    price_range_tnd="15 TND",
                    source_url="https://example.com/dup",
                    price_evidence="direct",
                    evidence_level="direct",
                    confidence="high",
                ),
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
                BenchmarkResearchSource(title="One", url="https://EXAMPLE.com/1?utm_campaign=spring#details", source_type="product_page"),
                BenchmarkResearchSource(title="Duplicate", url="https://example.com/1", source_type="product_page"),
            ],
        )

        validated = validate_provider_result(analysis, raw_sources=[])

        self.assertEqual([supplier.name for supplier in validated.tunisia_cheapest_suppliers], ["First", "Better Duplicate", "Second"])
        self.assertEqual(
            sum(1 for supplier in validated.tunisia_cheapest_suppliers if supplier.source_url == "https://example.com/dup"),
            1,
        )
        self.assertEqual([supplier.name for supplier in validated.china_cheapest_suppliers], ["C1", "C2", "C3"])
        self.assertEqual(len(validated.research_sources), 1)
        self.assertEqual(validated.research_sources[0].url, "https://example.com/1")

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

    def test_warnings_are_based_on_price_backed_results_not_row_count(self) -> None:
        analysis = ProviderAnalysisResult(
            tunisia_cheapest_suppliers=[
                TunisiaBenchmarkSupplier(
                    name="Priced 1",
                    price_min_tnd_numeric=10,
                    price_range_tnd="10 TND",
                    source_url="https://tunisia.example/1",
                    price_evidence="direct",
                    evidence_level="direct",
                    confidence="high",
                ),
                TunisiaBenchmarkSupplier(
                    name="Priced 2",
                    price_min_tnd_numeric=20,
                    price_range_tnd="20 TND",
                    source_url="https://tunisia.example/2",
                    price_evidence="direct",
                    evidence_level="direct",
                    confidence="high",
                ),
                TunisiaBenchmarkSupplier(
                    name="Missing Price",
                    source_url="https://tunisia.example/3",
                    price_evidence="snippet",
                    evidence_level="indirect",
                    confidence="medium",
                ),
            ],
            china_cheapest_suppliers=[
                ChinaBenchmarkSupplier(
                    name="China 1",
                    price_min_usd_numeric=1,
                    price_range_usd="US$1",
                    source_url="https://china.example/1?fbclid=abc",
                    price_evidence="direct",
                    moq_evidence="not_found",
                    evidence_level="direct",
                    confidence="high",
                ),
                ChinaBenchmarkSupplier(
                    name="China 2",
                    price_min_usd_numeric=2,
                    price_range_usd="US$2",
                    source_url="https://CHINA.example/2",
                    price_evidence="direct",
                    moq_evidence="not_found",
                    evidence_level="direct",
                    confidence="high",
                ),
                ChinaBenchmarkSupplier(
                    name="China Missing Price",
                    source_url="https://china.example/3",
                    price_evidence="snippet",
                    moq_evidence="not_found",
                    evidence_level="indirect",
                    confidence="medium",
                ),
            ],
        )

        validated = validate_provider_result(analysis, raw_sources=[])

        self.assertIn(
            "Fewer than 3 validated Tunisia price-backed supplier/source results were found.",
            validated.warnings,
        )
        self.assertIn(
            "Fewer than 3 validated China price-backed supplier/source results were found.",
            validated.warnings,
        )
