import unittest

from app.benchmark.query_strategy import build_regional_queries


class QueryStrategyTests(unittest.TestCase):
    def test_queries_are_capped_per_region_and_counted(self) -> None:
        queries = build_regional_queries("Vintage T9", max_queries_per_region=2)

        self.assertEqual(len(queries.tunisia), 2)
        self.assertEqual(len(queries.china), 2)
        self.assertEqual(queries.total_count, 4)
        self.assertIn("Vintage T9 prix Tunisie", queries.tunisia)
        self.assertIn("Vintage T9 China supplier price MOQ", queries.china)

    def test_query_cap_cannot_remove_all_queries(self) -> None:
        queries = build_regional_queries("portable blender", max_queries_per_region=0)

        self.assertEqual(len(queries.tunisia), 1)
        self.assertEqual(len(queries.china), 1)
