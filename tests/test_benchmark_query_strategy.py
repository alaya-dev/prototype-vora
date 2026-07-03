import unittest

from app.benchmark.query_strategy import build_regional_queries
from app.schemas import ProductUnderstanding


class QueryStrategyTests(unittest.TestCase):
    def test_queries_are_capped_per_region_and_counted(self) -> None:
        product = ProductUnderstanding(
            original_product="Vintage T9",
            normalized_product="T9 vintage hair trimmer",
            product_category="hair trimmer",
            brand_or_model="T9",
            english_search_name="T9 vintage hair trimmer",
            french_search_name="tondeuse cheveux T9 vintage",
            must_include_terms=["T9"],
        )
        queries = build_regional_queries(product, max_queries_per_region=2)

        self.assertEqual(len(queries.china_sourcing), 2)
        self.assertEqual(len(queries.tunisia_sourcing), 2)
        self.assertEqual(len(queries.tunisia_retail), 2)
        self.assertEqual(queries.total_count, 6)
        self.assertIn("T9 vintage hair trimmer cheapest wholesale unit price China", queries.china_sourcing)
        self.assertIn("tondeuse cheveux T9 vintage grossiste Tunisie prix", queries.tunisia_sourcing)
        self.assertIn("tondeuse cheveux T9 vintage prix Tunisie", queries.tunisia_retail)

    def test_query_cap_cannot_remove_all_queries(self) -> None:
        queries = build_regional_queries("portable blender", max_queries_per_region=0)

        self.assertEqual(len(queries.china_sourcing), 1)
        self.assertEqual(len(queries.tunisia_sourcing), 1)
        self.assertEqual(len(queries.tunisia_retail), 1)

    def test_china_queries_target_wholesale_product_prices_not_wholesaler_lists(self) -> None:
        queries = build_regional_queries("wireless earbuds hoco", max_queries_per_region=10)
        joined = " ".join(queries.china_sourcing).lower()

        self.assertIn("hoco wireless earbuds cheapest wholesale unit price china", joined)
        self.assertIn("lowest factory price moq", joined)
        self.assertIn("cheapest bulk price moq", joined)
        self.assertIn("alibaba lowest price moq", joined)
        self.assertIn("made-in-china lowest price moq", joined)
        self.assertIn("factory price moq", joined)
        self.assertIn("manufacturer price per piece", joined)
        self.assertNotIn("wholesale company", joined)
        self.assertNotIn("suppliers list", joined)

    def test_tunisia_sourcing_queries_target_b2b_and_import_prices(self) -> None:
        queries = build_regional_queries("LED strip lights", max_queries_per_region=10)
        joined = " ".join(queries.tunisia_sourcing).lower()

        self.assertIn("grossiste tunisie prix", joined)
        self.assertIn("prix gros tunisie", joined)
        self.assertIn("vente en gros tunisie", joined)
        self.assertIn("fournisseur tunisie prix gros", joined)
        self.assertIn("distributeur tunisie prix", joined)
        self.assertIn("importateur tunisie prix", joined)
        self.assertIn("fabricant tunisie prix", joined)
        self.assertIn("usine tunisie prix", joined)
        self.assertIn("b2b tunisie", joined)
        self.assertNotIn("jumia", joined)
        self.assertNotIn("boutique tunisie", joined)
        self.assertNotIn("achat tunisie", joined)

    def test_tunisia_retail_queries_keep_normal_local_price_terms(self) -> None:
        queries = build_regional_queries("LED strip lights", max_queries_per_region=20)
        joined = " ".join(queries.tunisia_retail).lower()

        self.assertIn("ruban led prix tunisie", joined)
        self.assertIn("achat tunisie", joined)
        self.assertIn("boutique tunisie", joined)
        self.assertIn("vente tunisie", joined)
        self.assertIn("site:.tn", joined)
        self.assertIn("jumia tunisie", joined)
        self.assertIn("boutique en ligne tunisie", joined)

    def test_tunisia_retail_queries_prioritize_known_retail_domains_under_small_caps(self) -> None:
        product = ProductUnderstanding(
            original_product="Vintage T9",
            normalized_product="T9 vintage hair trimmer",
            english_search_name="T9 vintage hair trimmer",
            french_search_name="tondeuse cheveux T9 vintage",
        )
        queries = build_regional_queries(product, max_queries_per_region=4)
        joined = " ".join(queries.tunisia_retail).lower()

        self.assertIn("tondeuse cheveux t9 vintage prix tunisie", joined)
        self.assertIn("vintage t9 prix tunisie", joined)
        self.assertIn("site:mytek.tn", joined)
        self.assertIn("vintage t9 site:mytek.tn", joined)

    def test_tunisia_retail_queries_keep_high_value_domains_before_broad_queries(self) -> None:
        product = ProductUnderstanding(
            original_product="Vintage T9",
            normalized_product="T9 vintage hair trimmer",
            english_search_name="T9 vintage hair trimmer",
            french_search_name="tondeuse cheveux T9 vintage",
        )
        queries = build_regional_queries(product, max_queries_per_region=10)
        joined = " ".join(queries.tunisia_retail).lower()

        self.assertIn("tondeuse cheveux t9 vintage site:mytek.tn", joined)
        self.assertIn("vintage t9 site:mytek.tn", joined)
        self.assertIn("tondeuse cheveux t9 vintage site:jumia.com.tn", joined)
        self.assertIn("vintage t9 site:jumia.com.tn", joined)
        self.assertIn("tondeuse cheveux t9 vintage site:tunisianet.com.tn", joined)
        self.assertNotIn("grossiste", joined)

    def test_product_intent_keeps_brand_model_and_category_terms(self) -> None:
        hoco = build_regional_queries("wireless earbuds hoco", max_queries_per_region=1)
        blender = build_regional_queries("portable blender", max_queries_per_region=1)

        self.assertIn("HOCO wireless earbuds", hoco.china_sourcing[0])
        self.assertIn("écouteurs sans fil HOCO", hoco.tunisia_sourcing[0])
        self.assertIn("portable blender", blender.china_sourcing[0])
        self.assertIn("mixeur portable", blender.tunisia_retail[0])

    def test_regional_brand_queries_include_exact_then_oem_equivalent_terms(self) -> None:
        queries = build_regional_queries("COALA RS2000W-IR 1500W Fan Heater", max_queries_per_region=10)
        joined = " ".join(queries.china_sourcing).lower()

        self.assertIn("coala rs2000w-ir 1500w fan heater", joined)
        self.assertIn("1500w 2000w ptc ceramic portable fan heater oem factory price moq", joined)
        self.assertIn("portable ptc ceramic fan heater 1500w manufacturer price", joined)
        self.assertIn("electric room heater 1500w 2000w factory wholesale moq", joined)
