import unittest

from app.benchmark.schemas import (
    BenchmarkResearchSource,
    ChinaBenchmarkSupplier,
    ChinaSourcingOffer,
    ProviderAnalysisResult,
    ProviderRawSource,
    TunisiaRetailMarket,
    TunisiaRetailOffer,
    TunisiaBenchmarkSupplier,
    TunisiaSourcingOffer,
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

    def test_product_match_downgrades_confidence(self) -> None:
        analysis = ProviderAnalysisResult(
            tunisia_cheapest_suppliers=[
                TunisiaBenchmarkSupplier(
                    name="Weak Match",
                    price_min_tnd_numeric=10,
                    price_range_tnd="10 TND",
                    source_url="https://tn.example/weak",
                    evidence_level="direct",
                    price_evidence="direct",
                    confidence="high",
                    product_match="weak",
                ),
                TunisiaBenchmarkSupplier(
                    name="Broad Match",
                    price_min_tnd_numeric=12,
                    price_range_tnd="12 TND",
                    source_url="https://tn.example/broad",
                    evidence_level="direct",
                    price_evidence="direct",
                    confidence="high",
                    product_match="broad",
                ),
            ]
        )

        validated = validate_provider_result(analysis, raw_sources=[])
        by_name = {supplier.name: supplier for supplier in validated.tunisia_cheapest_suppliers}

        self.assertEqual(by_name["Weak Match"].confidence, "low")
        self.assertEqual(by_name["Broad Match"].confidence, "medium")

    def test_china_product_match_affects_ranking_after_price_backing(self) -> None:
        analysis = ProviderAnalysisResult(
            china_cheapest_suppliers=[
                ChinaBenchmarkSupplier(
                    name="Weak Cheap",
                    price_min_usd_numeric=1,
                    price_range_usd="US$1",
                    source_url="https://china.example/weak",
                    price_evidence="direct",
                    evidence_level="direct",
                    confidence="high",
                    product_match="weak",
                ),
                ChinaBenchmarkSupplier(
                    name="Exact Slightly Higher",
                    price_min_usd_numeric=1.2,
                    price_range_usd="US$1.20",
                    source_url="https://china.example/exact",
                    price_evidence="direct",
                    evidence_level="direct",
                    confidence="high",
                    product_match="exact",
                ),
                ChinaBenchmarkSupplier(
                    name="Close",
                    price_min_usd_numeric=1.1,
                    price_range_usd="US$1.10",
                    source_url="https://china.example/close",
                    price_evidence="direct",
                    evidence_level="direct",
                    confidence="high",
                    product_match="close",
                ),
                ChinaBenchmarkSupplier(
                    name="No Price Exact",
                    source_url="https://china.example/no-price",
                    evidence_level="direct",
                    price_evidence="direct",
                    confidence="high",
                    product_match="exact",
                ),
            ]
        )

        validated = validate_provider_result(analysis, raw_sources=[])

        self.assertEqual(
            [supplier.name for supplier in validated.china_cheapest_suppliers],
            ["Close", "Exact Slightly Higher", "Weak Cheap"],
        )
        self.assertEqual(validated.china_cheapest_suppliers[-1].confidence, "low")

    def test_china_generic_supplier_without_product_price_is_downgraded(self) -> None:
        analysis = ProviderAnalysisResult(
            china_cheapest_suppliers=[
                ChinaBenchmarkSupplier(
                    name="Generic Supplier",
                    type="supplier_profile",
                    source_url="https://china.example/company",
                    evidence_level="direct",
                    price_evidence="direct",
                    confidence="high",
                    product_match="broad",
                )
            ]
        )

        validated = validate_provider_result(
            analysis,
            raw_sources=[
                ProviderRawSource(
                    url="https://china.example/company",
                    source_type="supplier_profile",
                    region_hint="china",
                )
            ],
        )
        supplier = validated.china_cheapest_suppliers[0]

        self.assertEqual(supplier.evidence_level, "weak")
        self.assertEqual(supplier.confidence, "low")
        self.assertEqual(supplier.price_evidence, "not_found")

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

    def test_three_phase_outputs_are_validated_separately(self) -> None:
        analysis = ProviderAnalysisResult(
            china_sourcing_offers=[
                ChinaSourcingOffer(name="C4", price_min_usd_numeric=4, price_range_usd="US$4", source_url="https://china.example/4", price_evidence="direct", evidence_level="direct", confidence="high", product_match="exact"),
                ChinaSourcingOffer(name="C1", price_min_usd_numeric=1, price_range_usd="US$1", source_url="https://china.example/1", price_evidence="direct", evidence_level="direct", confidence="high", product_match="exact"),
                ChinaSourcingOffer(name="C3", price_min_usd_numeric=3, price_range_usd="US$3", source_url="https://china.example/3", price_evidence="direct", evidence_level="direct", confidence="high", product_match="close"),
                ChinaSourcingOffer(name="C2", price_min_usd_numeric=2, price_range_usd="US$2", source_url="https://china.example/2", price_evidence="direct", evidence_level="direct", confidence="high", product_match="close"),
            ],
            tunisia_sourcing_offers=[
                TunisiaSourcingOffer(name="TS3", type="wholesaler", price_min_tnd_numeric=30, price_range_tnd="30 TND", source_url="https://tn.example/source-3", price_evidence="direct", evidence_level="direct", confidence="high", product_match="exact", notes="prix de gros"),
                TunisiaSourcingOffer(name="TS1", type="wholesaler", price_min_tnd_numeric=10, price_range_tnd="10 TND", source_url="https://tn.example/source-1", price_evidence="direct", evidence_level="direct", confidence="high", product_match="exact", notes="prix de gros"),
                TunisiaSourcingOffer(name="TS2", type="distributor", price_min_tnd_numeric=20, price_range_tnd="20 TND", source_url="https://tn.example/source-2", price_evidence="direct", evidence_level="direct", confidence="high", product_match="close", notes="prix de gros"),
                TunisiaSourcingOffer(name="Retail fallback", type="marketplace_source", price_min_tnd_numeric=5, price_range_tnd="5 TND", source_url="https://tn.example/retail", price_evidence="direct", evidence_level="direct", confidence="high", product_match="exact"),
            ],
            tunisia_retail_market=TunisiaRetailMarket(
                retail_offers=[
                    TunisiaRetailOffer(seller_name="Seller B", price_min_tnd_numeric=25, price_range_tnd="25 TND", source_url="https://shop-b.example/item", price_evidence="direct", evidence_level="direct", confidence="high", product_match="exact"),
                    TunisiaRetailOffer(seller_name="Seller A", price_min_tnd_numeric=15, price_range_tnd="15 TND", source_url="https://shop-a.example/item", price_evidence="direct", evidence_level="direct", confidence="high", product_match="exact"),
                    TunisiaRetailOffer(seller_name="Seller C", price_min_tnd_numeric=35, price_range_tnd="35 TND", source_url="https://shop-c.example/item", price_evidence="direct", evidence_level="direct", confidence="high", product_match="close"),
                ]
            ),
        )

        validated = validate_provider_result(analysis, raw_sources=[])

        self.assertEqual([offer.name for offer in validated.china_sourcing_offers], ["C1", "C2", "C3"])
        self.assertEqual([offer.name for offer in validated.tunisia_sourcing_offers], ["TS1", "TS2", "TS3"])
        self.assertEqual([offer.seller_name for offer in validated.tunisia_retail_market.retail_offers], ["Retail fallback", "Seller A", "Seller B", "Seller C"])
        self.assertEqual(validated.tunisia_retail_market.price_min_tnd, 5)
        self.assertEqual(validated.tunisia_retail_market.price_max_tnd, 35)
        self.assertEqual(validated.tunisia_retail_market.price_avg_tnd, 20)
        self.assertEqual(validated.tunisia_retail_market.unique_sellers_count, 4)
        self.assertEqual(validated.tunisia_retail_market.retail_sources_count, 4)
        self.assertEqual(validated.tunisia_retail_market.seller_density, "medium")

    def test_tunisia_retail_intervals_use_both_endpoints_and_midpoint_average(self) -> None:
        analysis = ProviderAnalysisResult(
            tunisia_retail_market=TunisiaRetailMarket(
                retail_offers=[
                    TunisiaRetailOffer(
                        seller_name="Mytek",
                        price_range_tnd="4.000 - 69.000 TND",
                        source_url="https://mytek.tn/639-support-voiture-tunisie",
                        price_evidence="direct",
                        evidence_level="direct",
                        confidence="high",
                        product_match="broad",
                    ),
                    TunisiaRetailOffer(
                        seller_name="Spacenet",
                        price_range_tnd="7.900 - 339.000 DT",
                        source_url="https://spacenet.tn/support-voiture.html",
                        price_evidence="direct",
                        evidence_level="direct",
                        confidence="high",
                        product_match="broad",
                    ),
                ]
            )
        )

        validated = validate_provider_result(analysis, raw_sources=[])
        offers = {offer.seller_name: offer for offer in validated.tunisia_retail_market.retail_offers}

        self.assertEqual(offers["Mytek"].price_min_tnd_numeric, 4)
        self.assertEqual(offers["Mytek"].price_max_tnd_numeric, 69)
        self.assertEqual(offers["Mytek"].price_range_tnd, "4–69 TND")
        self.assertEqual(offers["Mytek"].source_price_type, "range")
        self.assertEqual(offers["Mytek"].source_page_type, "category_or_listing")
        self.assertEqual(offers["Spacenet"].price_min_tnd_numeric, 7.9)
        self.assertEqual(offers["Spacenet"].price_max_tnd_numeric, 339)
        self.assertEqual(offers["Spacenet"].price_range_tnd, "7.9–339 TND")
        self.assertEqual(validated.tunisia_retail_market.price_min_tnd, 4)
        self.assertEqual(validated.tunisia_retail_market.price_max_tnd, 339)
        self.assertEqual(validated.tunisia_retail_market.price_avg_tnd, 104.97)
        self.assertIn(
            "Some prices come from category/listing ranges, not exact product pages.",
            validated.tunisia_retail_market.competition_notes,
        )

    def test_tunisia_sourcing_excludes_foreign_and_retail_sources(self) -> None:
        analysis = ProviderAnalysisResult(
            tunisia_sourcing_offers=[
                TunisiaSourcingOffer(name="Algeria", price_min_tnd_numeric=10, price_range_tnd="10 TND", source_url="https://supplier.dz/item", price_evidence="direct", evidence_level="direct", confidence="high", product_match="exact"),
                TunisiaSourcingOffer(name="Morocco", price_min_tnd_numeric=11, price_range_tnd="11 TND", source_url="https://supplier.ma/item", price_evidence="direct", evidence_level="direct", confidence="high", product_match="exact"),
                TunisiaSourcingOffer(name="France", price_min_tnd_numeric=12, price_range_tnd="12 TND", source_url="https://supplier.fr/item", price_evidence="direct", evidence_level="direct", confidence="high", product_match="exact"),
                TunisiaSourcingOffer(name="Retail shop", type="marketplace_source", price_min_tnd_numeric=5, price_range_tnd="5 TND", source_url="https://shop.tn/item", price_evidence="direct", evidence_level="direct", confidence="high", product_match="exact"),
                TunisiaSourcingOffer(name="Valid grossiste", type="wholesaler", price_min_tnd_numeric=20, price_range_tnd="prix gros 20 TND", source_url="https://grossiste.tn/item", price_evidence="direct", evidence_level="direct", confidence="high", product_match="exact"),
            ],
            tunisia_retail_market=TunisiaRetailMarket(
                retail_offers=[
                    TunisiaRetailOffer(seller_name="Retail shop", price_min_tnd_numeric=5, price_range_tnd="5 TND", source_url="https://shop.tn/item", price_evidence="direct", evidence_level="direct", confidence="high", product_match="exact")
                ]
            ),
        )
        raw_sources = [
            ProviderRawSource(title="Algerie grossiste", url="https://supplier.dz/item", snippet="grossiste Algerie", content="grossiste Algerie"),
            ProviderRawSource(title="Maroc grossiste", url="https://supplier.ma/item", snippet="grossiste Maroc", content="grossiste Maroc"),
            ProviderRawSource(title="France grossiste", url="https://supplier.fr/item", snippet="grossiste France", content="grossiste France"),
            ProviderRawSource(title="Boutique Tunisie", url="https://shop.tn/item", snippet="achat panier livraison boutique Tunisie", content="achat panier livraison boutique Tunisie"),
            ProviderRawSource(title="Grossiste Tunisie", url="https://grossiste.tn/item", snippet="grossiste Tunisie prix gros", content="grossiste Tunisie prix gros produit 20 TND"),
        ]

        validated = validate_provider_result(analysis, raw_sources=raw_sources)

        self.assertEqual([offer.name for offer in validated.tunisia_sourcing_offers], ["Valid grossiste"])
        self.assertEqual([offer.seller_name for offer in validated.tunisia_retail_market.retail_offers], ["Retail shop"])

    def test_no_tunisia_wholesale_returns_clean_not_found_message(self) -> None:
        analysis = ProviderAnalysisResult(
            tunisia_sourcing_offers=[
                TunisiaSourcingOffer(name="Retail only", type="marketplace_source", price_min_tnd_numeric=90, price_range_tnd="90 TND", source_url="https://retail.tn/item", price_evidence="direct", evidence_level="direct", confidence="high", product_match="exact")
            ],
            tunisia_retail_market=TunisiaRetailMarket(
                retail_offers=[
                    TunisiaRetailOffer(seller_name="Retail only", price_min_tnd_numeric=90, price_range_tnd="90 TND", source_url="https://retail.tn/item", price_evidence="direct", evidence_level="direct", confidence="high", product_match="exact")
                ]
            ),
        )
        raw_sources = [
            ProviderRawSource(title="Boutique", url="https://retail.tn/item", snippet="achat boutique livraison", content="achat boutique livraison")
        ]

        validated = validate_provider_result(analysis, raw_sources=raw_sources)

        self.assertEqual(validated.tunisia_sourcing_offers, [])
        self.assertIn(
            "No source-backed Tunisian wholesale/importer/distributor/manufacturer offer was found for this product.",
            validated.warnings,
        )
        self.assertEqual(
            validated.missing_data.tunisia_sourcing,
            "No reliable Tunisian wholesale sourcing price was found. Retail prices were kept separate in the Tunisia retail market section.",
        )

    def test_french_source_about_tunisia_cannot_be_high_confidence_sourcing(self) -> None:
        analysis = ProviderAnalysisResult(
            tunisia_sourcing_offers=[
                TunisiaSourcingOffer(name="France about Tunisia", type="distributor", price_min_tnd_numeric=20, price_range_tnd="20 TND", source_url="https://example.fr/tunisie-item", price_evidence="direct", evidence_level="direct", confidence="high", product_match="exact")
            ]
        )
        raw_sources = [
            ProviderRawSource(title="Distributeur Tunisie", url="https://example.fr/tunisie-item", snippet="distributeur Tunisie prix gros", content="distributeur Tunisie prix gros")
        ]

        validated = validate_provider_result(analysis, raw_sources=raw_sources)

        self.assertEqual(len(validated.tunisia_sourcing_offers), 1)
        self.assertEqual(validated.tunisia_sourcing_offers[0].confidence, "medium")

    def test_tunisian_decimal_price_formats_are_normalized(self) -> None:
        analysis = ProviderAnalysisResult(
            tunisia_retail_market=TunisiaRetailMarket(
                retail_offers=[
                    TunisiaRetailOffer(seller_name="Mytek", price_range_tnd="14,900 TND", price_min_tnd_numeric=14900, source_url="https://mytek.tn/t9", price_evidence="direct", evidence_level="direct", confidence="high", product_match="exact"),
                    TunisiaRetailOffer(seller_name="Keyshop", price_range_tnd="35,000 TND", price_min_tnd_numeric=35000, source_url="https://keyshop-tn.com/t9", price_evidence="direct", evidence_level="direct", confidence="high", product_match="exact"),
                    TunisiaRetailOffer(seller_name="Shopiwell", price_range_tnd="43,600 TND", price_min_tnd_numeric=43600, source_url="https://shopiwell.tn/t9", price_evidence="direct", evidence_level="direct", confidence="high", product_match="exact"),
                    TunisiaRetailOffer(seller_name="Expensive", price_range_tnd="1 200 TND", price_min_tnd_numeric=1200, source_url="https://expensive.tn/t9", price_evidence="direct", evidence_level="direct", confidence="high", product_match="exact"),
                ]
            )
        )

        validated = validate_provider_result(analysis, raw_sources=[])
        offers = {offer.seller_name: offer for offer in validated.tunisia_retail_market.retail_offers}

        self.assertEqual(offers["Mytek"].price_min_tnd_numeric, 14.9)
        self.assertEqual(offers["Mytek"].price_range_tnd, "14.9 TND")
        self.assertEqual(offers["Mytek"].original_price_text, "14,900 TND")
        self.assertEqual(offers["Keyshop"].price_min_tnd_numeric, 35.0)
        self.assertEqual(offers["Shopiwell"].price_min_tnd_numeric, 43.6)
        self.assertEqual(offers["Expensive"].price_min_tnd_numeric, 1200)

    def test_t9_retail_listings_keep_their_observed_prices(self) -> None:
        analysis = ProviderAnalysisResult(
            tunisia_retail_market=TunisiaRetailMarket(
                retail_offers=[
                    TunisiaRetailOffer(
                        seller_name="MyTek",
                        product_title="Tondeuse TRIMMER VINTAGE - Gold",
                        price_range_tnd="19,90 TND",
                        price_min_tnd_numeric=19.90,
                        source_url="https://www.mytek.tn/tondeuse-a-cheveux-trimmer-vintage.html",
                    ),
                    TunisiaRetailOffer(
                        seller_name="Last Price Tunisie",
                        product_title="Tondeuse Cheveux Professionnel VINTAGE T9",
                        price_range_tnd="9,90 TND",
                        price_min_tnd_numeric=9.90,
                        source_url="https://lastprice.tn/tondeuse-t9",
                    ),
                ]
            )
        )

        validated = validate_provider_result(analysis, raw_sources=[])
        offers = {offer.seller_name: offer for offer in validated.tunisia_retail_market.retail_offers}

        self.assertEqual(offers["MyTek"].price_min_tnd_numeric, 9.90)
        self.assertEqual(offers["Last Price Tunisie"].price_min_tnd_numeric, 19.90)
        self.assertEqual(validated.tunisia_retail_market.price_min_tnd, 9.90)
        self.assertEqual(validated.tunisia_retail_market.price_max_tnd, 19.90)
