import unittest

from app.benchmark.query_strategy import build_regional_queries


class QueryStrategyTests(unittest.TestCase):
    def test_queries_are_capped_per_region_and_counted(self) -> None:
        queries = build_regional_queries("Vintage T9", max_queries_per_region=2)

        self.assertEqual(len(queries.tunisia), 2)
        self.assertEqual(len(queries.china), 2)
        self.assertEqual(queries.total_count, 4)
        self.assertIn("T9 vintage hair trimmer prix Tunisie", queries.tunisia)
        self.assertIn("T9 vintage hair trimmer wholesale unit price China", queries.china)

    def test_query_cap_cannot_remove_all_queries(self) -> None:
        queries = build_regional_queries("portable blender", max_queries_per_region=0)

        self.assertEqual(len(queries.tunisia), 1)
        self.assertEqual(len(queries.china), 1)

    def test_china_queries_target_wholesale_product_prices_not_wholesaler_lists(self) -> None:
        queries = build_regional_queries("wireless earbuds hoco", max_queries_per_region=9)
        joined = " ".join(queries.china).lower()

        self.assertIn("hoco wireless earbuds wholesale unit price china", joined)
        self.assertIn("factory wholesale price", joined)
        self.assertIn("bulk price moq", joined)
        self.assertIn("oem odm wholesale price", joined)
        self.assertIn("alibaba wholesale price moq", joined)
        self.assertNotIn("wholesale company", joined)
        self.assertNotIn("suppliers list", joined)

    def test_tunisia_queries_keep_normal_local_price_terms(self) -> None:
        queries = build_regional_queries("LED strip lights", max_queries_per_region=6)
        joined = " ".join(queries.tunisia).lower()

        self.assertIn("led strip lights prix tunisie", joined)
        self.assertIn("achat tunisie", joined)
        self.assertIn("boutique tunisie", joined)
        self.assertIn("vente tunisie", joined)
        self.assertIn("site:.tn", joined)

    def test_product_intent_keeps_brand_model_and_category_terms(self) -> None:
        hoco = build_regional_queries("wireless earbuds hoco", max_queries_per_region=1)
        blender = build_regional_queries("portable blender", max_queries_per_region=1)

        self.assertIn("HOCO wireless earbuds", hoco.china[0])
        self.assertIn("mini portable blender", blender.china[0])
