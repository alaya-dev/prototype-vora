import tempfile
import unittest
from pathlib import Path

from app.prototype.schemas import CostConfig
from app.prototype.storage import PrototypeStore


class PrototypeStorageTests(unittest.TestCase):
    def test_cost_config_updates_estimated_research_cost(self) -> None:
        store = PrototypeStore(_temp_db())
        store.save_cost_config(
            CostConfig(
                firecrawl_cost_per_call=0.10,
                tavily_cost_per_call=0.20,
                exa_cost_per_call=0.30,
                gemini_intent_cost_per_call=0.05,
                gemini_analysis_cost_per_call=0.15,
                usd_to_tnd_rate=3.1,
            )
        )
        run_id = store.create_run(
            product_input="Vintage T9",
            normalized_product="T9 vintage hair trimmer",
            status="success",
            latency_ms=1200,
            warnings=[],
            errors=[],
        )
        store.log_provider_attempt(run_id, "firecrawl", "china_sourcing", "success", 2, 5, 200)
        store.log_provider_attempt(run_id, "tavily", "tunisia_sourcing", "success", 1, 3, 100)
        store.log_api_usage(run_id, "gemini_intent", 1)
        store.log_api_usage(run_id, "gemini_analysis", 1)

        detail = store.get_run_detail(run_id)
        runs = store.list_runs()
        summary = store.get_summary()

        self.assertAlmostEqual(detail.estimated_research_cost_usd, 0.60)
        self.assertAlmostEqual(runs[0].estimated_research_cost_usd, 0.60)
        self.assertEqual(summary.total_runs, 1)
        self.assertEqual(detail.firecrawl_called, True)
        self.assertEqual(detail.tavily_called, True)
        self.assertEqual(detail.exa_called, False)
        self.assertNotIn("api_key", str(detail.model_dump()).lower())

    def test_sourcing_agents_crud_returns_only_active_for_reveal(self) -> None:
        store = PrototypeStore(_temp_db())
        active_id = store.upsert_sourcing_agent({"name": "Active", "active": True})
        inactive_id = store.upsert_sourcing_agent({"name": "Inactive", "active": False})

        all_agents = store.list_sourcing_agents(active_only=False)
        active_agents = store.list_sourcing_agents(active_only=True)
        store.delete_sourcing_agent(inactive_id)

        self.assertEqual({agent.id for agent in all_agents}, {active_id, inactive_id})
        self.assertEqual([agent.name for agent in active_agents], ["Active"])
        self.assertEqual([agent.id for agent in store.list_sourcing_agents(active_only=False)], [active_id])


def _temp_db() -> Path:
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    handle.close()
    return Path(handle.name)
