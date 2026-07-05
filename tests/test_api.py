import importlib
import unittest

from fastapi.testclient import TestClient

from app.benchmark.schemas import (
    BenchmarkAnalyzeResponse,
    BenchmarkComparisonSummary,
    BenchmarkProviderRun,
    ProviderInfo,
    ProvidersResponse,
)
from app.config import Settings
from app.prototype.schemas import (
    ContactSellerCard,
    CostConfig,
    PrototypeAnalyzeResponse,
    PrototypeRevealResponse,
    RetailMarketSummary,
    SourcingSummary,
)
from app.schemas import IntentResult, ProductAnalysisResponse


class StubBenchmarkPipeline:
    def __init__(self, response: BenchmarkAnalyzeResponse) -> None:
        self.response = response
        self.calls = []

    async def analyze(
        self,
        product: str,
        providers: list[str],
    ) -> BenchmarkAnalyzeResponse:
        self.calls.append((product, providers))
        return self.response


class StubLegacyPipeline:
    def __init__(self) -> None:
        self.calls = []

    async def analyze(
        self,
        product: str,
        category: str | None = None,
    ) -> ProductAnalysisResponse:
        self.calls.append((product, category))
        return ProductAnalysisResponse(
            product=product,
            is_valid_product=False,
            intent_reason="Compatibility route.",
            market_summary="",
        )


class StubPrototypeOrchestrator:
    def __init__(self) -> None:
        self.calls = []

    async def analyze(self, request):
        self.calls.append(request)
        return PrototypeAnalyzeResponse(
            run_id="run_1",
            product_understanding={},
            product_image_url=None,
            product_description="Source-backed analysis.",
            sourcing_summary=SourcingSummary(
                china_price_range="US$2-3",
                tunisia_wholesale_summary="No reliable Tunisian wholesale sourcing offer was found for this product.",
                tunisia_wholesale_found=False,
            ),
            retail_market_summary=RetailMarketSummary(
                retail_price_range_tnd="35-42 TND",
                retail_min_tnd=35,
                retail_max_tnd=42,
                retail_avg_tnd=38.5,
                seller_density="low",
            ),
            recommendation="investigate_more",
            recommendation_reason="Tunisia wholesale evidence is missing.",
            go_reveal_available=True,
            links_hidden=True,
        )

    async def reveal(self, run_id: str):
        return PrototypeRevealResponse(
            run_id=run_id,
            seller_contacts=[
                ContactSellerCard(
                    seller_name="CN",
                    company_name="CN Factory",
                    email="sales@example.com",
                    contact_confidence="medium",
                )
            ],
            tunisia_sourcing_links=[],
            sourcing_agents=[],
        )


class ApiTests(unittest.TestCase):
    def test_providers_returns_status_without_secrets(self) -> None:
        server_module = importlib.import_module("server")
        app = server_module.create_app(
            settings=_settings(),
            benchmark_pipeline=_benchmark_pipeline(),
            provider_infos=ProvidersResponse(
                providers=[
                    ProviderInfo(
                        provider_id="brave",
                        provider_name="Brave Search + Gemini",
                        configured=False,
                        requires_gemini_analysis=True,
                        production_risk="medium",
                        missing_config=["BRAVE_SEARCH_API_KEY"],
                    )
                ],
                global_missing_config=["GEMINI_INTENT_API_KEY"],
            ),
        )
        response = TestClient(app).get("/providers")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["providers"][0]["missing_config"], ["BRAVE_SEARCH_API_KEY"])
        self.assertNotIn("key-value", str(body).lower())

    def test_benchmark_analyze_forwards_product_and_providers(self) -> None:
        server_module = importlib.import_module("server")
        pipeline = _benchmark_pipeline()
        app = server_module.create_app(
            settings=_settings(),
            benchmark_pipeline=pipeline,
            provider_infos=ProvidersResponse(providers=[]),
        )

        response = TestClient(app).post(
            "/benchmark/analyze",
            json={"product": "Vintage T9", "providers": ["brave"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(pipeline.calls, [("Vintage T9", ["brave"])])
        self.assertEqual(response.json()["intent"]["is_valid_product"], True)

    def test_old_analyze_route_stays_available_for_compatibility(self) -> None:
        server_module = importlib.import_module("server")
        legacy = StubLegacyPipeline()
        app = server_module.create_app(
            settings=_settings(),
            pipeline=legacy,
            benchmark_pipeline=_benchmark_pipeline(),
            provider_infos=ProvidersResponse(providers=[]),
        )

        response = TestClient(app).post("/analyze", json={"product": "hello"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(legacy.calls, [("hello", None)])

    def test_benchmark_response_contains_usage_fields(self) -> None:
        server_module = importlib.import_module("server")
        app = server_module.create_app(
            settings=_settings(),
            benchmark_pipeline=_benchmark_pipeline(),
            provider_infos=ProvidersResponse(providers=[]),
        )

        response = TestClient(app).post(
            "/benchmark/analyze",
            json={"product": "Vintage T9", "providers": ["brave"]},
        )
        run = response.json()["runs"][0]

        self.assertIn("provider_api_calls", run)
        self.assertIn("gemini_intent_calls", run)
        self.assertIn("gemini_analysis_calls", run)
        self.assertIn("raw_queries_count", run)
        self.assertIn("cost_notes", run)
        self.assertIn("production_risk", run)

    def test_prototype_analyze_and_reveal_routes(self) -> None:
        server_module = importlib.import_module("server")
        prototype = StubPrototypeOrchestrator()
        app = server_module.create_app(
            settings=_settings(),
            benchmark_pipeline=_benchmark_pipeline(),
            provider_infos=ProvidersResponse(providers=[]),
            prototype_orchestrator=prototype,
        )

        analyze_response = TestClient(app).post(
            "/prototype/analyze",
            json={"product": "Vintage T9 hair trimmer", "quantity_scenarios": [1000]},
        )
        reveal_response = TestClient(app).get("/prototype/runs/run_1/reveal")

        self.assertEqual(analyze_response.status_code, 200)
        self.assertTrue(analyze_response.json()["links_hidden"])
        self.assertIn("decision_scores", analyze_response.json())
        scores = analyze_response.json()["decision_scores"]
        self.assertEqual(scores["go_percent"] + scores["no_go_percent"], 100)
        self.assertIn("decision_summary", analyze_response.json())
        self.assertIn("positive_signals", analyze_response.json())
        self.assertIn("risk_signals", analyze_response.json())
        self.assertIn("main_decision_factors", analyze_response.json())
        self.assertEqual(analyze_response.json()["analysis_quantity_units"], 1000)
        self.assertNotIn("china_sourcing_links", analyze_response.text)
        self.assertNotIn("cn.example", analyze_response.text.lower())
        self.assertEqual(reveal_response.status_code, 200)
        self.assertEqual(reveal_response.json()["china_sourcing_links"], [])
        self.assertEqual(reveal_response.json()["seller_contacts"][0]["email"], "sales@example.com")
        self.assertNotIn("cn.example", reveal_response.text.lower())

    def test_analytics_and_agent_routes_do_not_expose_keys(self) -> None:
        server_module = importlib.import_module("server")
        app = server_module.create_app(
            settings=_settings(tavily_api_key="secret-tvly"),
            benchmark_pipeline=_benchmark_pipeline(),
            provider_infos=ProvidersResponse(providers=[]),
        )
        client = TestClient(app)

        cost_response = client.post(
            "/api/analytics/cost-config",
            json=CostConfig(firecrawl_cost_per_call=0.1).model_dump(),
        )
        agent_response = client.post(
            "/api/sourcing-agents",
            json={"name": "Amina", "email": "amina@example.com", "active": True},
        )
        summary_response = client.get("/api/analytics/summary")

        self.assertEqual(cost_response.status_code, 200)
        self.assertEqual(agent_response.status_code, 200)
        self.assertEqual(summary_response.status_code, 200)
        combined = cost_response.text + agent_response.text + summary_response.text
        self.assertNotIn("secret-tvly", combined)

    def test_analytics_api_requires_admin_password_when_configured(self) -> None:
        server_module = importlib.import_module("server")
        app = server_module.create_app(
            settings=_settings(admin_dashboard_password="admin-secret"),
            benchmark_pipeline=_benchmark_pipeline(),
            provider_infos=ProvidersResponse(providers=[]),
        )
        client = TestClient(app)

        self.assertEqual(client.get("/api/analytics/summary").status_code, 401)
        self.assertEqual(
            client.get("/api/analytics/summary", headers={"x-admin-password": "wrong"}).status_code,
            401,
        )
        self.assertEqual(
            client.get("/api/analytics/summary", headers={"x-admin-password": "admin-secret"}).status_code,
            200,
        )
        self.assertEqual(
            client.get("/api/sourcing-agents", headers={"x-admin-password": "admin-secret"}).status_code,
            200,
        )


def _benchmark_pipeline() -> StubBenchmarkPipeline:
    return StubBenchmarkPipeline(
        BenchmarkAnalyzeResponse(
            product="Vintage T9",
            normalized_product="Vintage T9",
            intent=IntentResult(
                is_valid_product=True,
                normalized_product="Vintage T9",
                reason="Valid.",
            ),
            runs=[
                BenchmarkProviderRun(
                    provider_id="brave",
                    provider_name="Brave Search + Gemini",
                    status="success",
                    production_risk="medium",
                )
            ],
            comparison_summary=BenchmarkComparisonSummary(
                notes="Directional comparison."
            ),
        )
    )


def _settings(**overrides) -> Settings:
    values = dict(
        gemini_intent_api_key="intent-key",
        gemini_intent_model="gemini-3.1-flash-lite",
        gemini_analysis_api_key="analysis-key",
        gemini_analysis_model="gemini-3.1-flash-lite",
        gemini_api_key="test-gemini",
        gemini_model="gemini-3.1-flash-lite",
        analysis_timeout_seconds=45,
        benchmark_provider_timeout_seconds=45,
        benchmark_max_providers_parallel=8,
        search_results_per_query=10,
        search_queries_per_region=4,
        max_raw_sources_per_provider=20,
    )
    values.update(overrides)
    return Settings(
        **values
    )
