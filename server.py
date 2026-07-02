from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.agents.china_supplier_research import GeminiChinaSupplierResearchAgent
from app.agents.intent_classifier import IntentClassifierAgent
from app.agents.market_research import GeminiTunisiaResearchAgent
from app.benchmark.pipeline import BenchmarkPipeline
from app.benchmark.providers import build_provider_registry
from app.benchmark.providers.exa import ExaAdapter
from app.benchmark.providers.firecrawl import FirecrawlAdapter
from app.benchmark.providers.tavily import TavilyAdapter
from app.benchmark.schemas import (
    BenchmarkAnalyzeRequest,
    BenchmarkAnalyzeResponse,
    ProvidersResponse,
)
from app.config import Settings
from app.pipeline import PipelineError, PipelineTimeoutError, ProductAnalysisPipeline
from app.prototype.research_orchestrator import PrototypeResearchOrchestrator
from app.prototype.schemas import (
    AnalyticsRunDetail,
    AnalyticsRunSummary,
    AnalyticsSummary,
    CostConfig,
    PrototypeAnalyzeRequest,
    PrototypeAnalyzeResponse,
    PrototypeRevealResponse,
    SourcingAgent,
)
from app.prototype.storage import PrototypeStore
from app.schemas import AnalyzeRequest, ProductAnalysisResponse
from app.services.gemini_client import (
    GeminiAnalysisClient,
    GeminiClient,
    GeminiClientError,
    GeminiIntentClient,
)
from app.services.gemini_search_client import GeminiSearchClient, GeminiSearchClientError


def create_app(
    settings: Settings | None = None,
    pipeline: ProductAnalysisPipeline | None = None,
    benchmark_pipeline: BenchmarkPipeline | None = None,
    provider_infos: ProvidersResponse | None = None,
    prototype_orchestrator: PrototypeResearchOrchestrator | None = None,
    prototype_store: PrototypeStore | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    provider_registry = build_provider_registry(resolved_settings)
    resolved_provider_infos = provider_infos or _build_provider_infos(
        resolved_settings,
        provider_registry,
    )
    resolved_benchmark_pipeline = benchmark_pipeline or _build_benchmark_pipeline(
        resolved_settings,
        provider_registry,
    )
    resolved_pipeline = pipeline or _build_pipeline_or_none(resolved_settings)
    resolved_store = prototype_store or PrototypeStore()
    resolved_prototype_orchestrator = prototype_orchestrator or _build_prototype_orchestrator(
        resolved_settings,
        resolved_store,
    )

    app = FastAPI(title="VORA API", version="2.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/providers", response_model=ProvidersResponse)
    async def providers() -> ProvidersResponse:
        return resolved_provider_infos

    @app.post("/benchmark/analyze", response_model=BenchmarkAnalyzeResponse)
    async def benchmark_analyze(
        request: BenchmarkAnalyzeRequest,
    ) -> BenchmarkAnalyzeResponse:
        try:
            return await resolved_benchmark_pipeline.analyze(
                request.product,
                request.providers,
            )
        except RuntimeError as error:
            message = str(error)
            if message.startswith("GEMINI_"):
                raise HTTPException(status_code=503, detail=message) from error
            raise

    @app.post("/analyze", response_model=ProductAnalysisResponse)
    async def analyze(request: AnalyzeRequest) -> ProductAnalysisResponse:
        if resolved_pipeline is None:
            raise HTTPException(
                status_code=503,
                detail="Legacy /analyze is unavailable because GEMINI_API_KEY is not configured.",
            )
        try:
            return await resolved_pipeline.analyze(request.product, request.category)
        except PipelineTimeoutError as error:
            raise HTTPException(status_code=504, detail=str(error)) from error
        except (PipelineError, GeminiClientError, GeminiSearchClientError) as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.post("/prototype/analyze", response_model=PrototypeAnalyzeResponse)
    async def prototype_analyze(
        request: PrototypeAnalyzeRequest,
    ) -> PrototypeAnalyzeResponse:
        try:
            resolved_prototype_orchestrator.cost_config = resolved_store.get_cost_config()
            return await resolved_prototype_orchestrator.analyze(request)
        except RuntimeError as error:
            message = str(error)
            if message.startswith("GEMINI_"):
                raise HTTPException(status_code=503, detail=message) from error
            raise HTTPException(status_code=502, detail="Prototype analysis failed.") from error

    @app.get("/prototype/runs/{run_id}/reveal", response_model=PrototypeRevealResponse)
    async def prototype_reveal(run_id: str) -> PrototypeRevealResponse:
        try:
            return await resolved_prototype_orchestrator.reveal(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Prototype run not found.") from error

    @app.get("/api/analytics/runs", response_model=list[AnalyticsRunSummary])
    async def analytics_runs() -> list[AnalyticsRunSummary]:
        return resolved_store.list_runs()

    @app.get("/api/analytics/runs/{run_id}", response_model=AnalyticsRunDetail)
    async def analytics_run_detail(run_id: str) -> AnalyticsRunDetail:
        try:
            return resolved_store.get_run_detail(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Prototype run not found.") from error

    @app.get("/api/analytics/summary", response_model=AnalyticsSummary)
    async def analytics_summary() -> AnalyticsSummary:
        return resolved_store.get_summary()

    @app.get("/api/analytics/cost-config", response_model=CostConfig)
    async def get_cost_config() -> CostConfig:
        return resolved_store.get_cost_config()

    @app.post("/api/analytics/cost-config", response_model=CostConfig)
    async def save_cost_config(config: CostConfig) -> CostConfig:
        saved = resolved_store.save_cost_config(config)
        resolved_prototype_orchestrator.cost_config = saved
        return saved

    @app.get("/api/sourcing-agents", response_model=list[SourcingAgent])
    async def list_sourcing_agents(active_only: bool = False) -> list[SourcingAgent]:
        return resolved_store.list_sourcing_agents(active_only=active_only)

    @app.post("/api/sourcing-agents", response_model=SourcingAgent)
    async def create_sourcing_agent(agent: SourcingAgent) -> SourcingAgent:
        agent_id = resolved_store.upsert_sourcing_agent(agent.model_dump(exclude={"id"}))
        return resolved_store.list_sourcing_agents(active_only=False)[-1].model_copy(update={"id": agent_id})

    @app.put("/api/sourcing-agents/{agent_id}", response_model=SourcingAgent)
    async def update_sourcing_agent(agent_id: int, agent: SourcingAgent) -> SourcingAgent:
        resolved_store.upsert_sourcing_agent(agent.model_dump(exclude={"id"}), agent_id=agent_id)
        for item in resolved_store.list_sourcing_agents(active_only=False):
            if item.id == agent_id:
                return item
        raise HTTPException(status_code=404, detail="Sourcing agent not found.")

    @app.delete("/api/sourcing-agents/{agent_id}")
    async def delete_sourcing_agent(agent_id: int) -> dict[str, bool]:
        resolved_store.delete_sourcing_agent(agent_id)
        return {"deleted": True}

    @app.get("/analytics", response_class=HTMLResponse)
    async def analytics_page() -> str:
        with open("static/index.html", "r", encoding="utf-8") as file:
            return file.read()

    app.mount("/", StaticFiles(directory="static", html=True), name="static")
    return app


class MissingGeminiRoleClient:
    def __init__(self, variable_name: str) -> None:
        self.variable_name = variable_name

    async def classify(self, product: str):
        raise RuntimeError(f"{self.variable_name} is required for benchmark analysis.")

    async def extract(self, product: str, evidence):
        raise RuntimeError(
            f"{self.variable_name} is required for Gemini-based provider analysis."
        )

    async def extract_client_analysis(self, product, evidence, cost_config, quantity_scenarios):
        raise RuntimeError(
            f"{self.variable_name} is required for prototype client analysis."
        )


def _build_provider_infos(
    settings: Settings,
    provider_registry,
) -> ProvidersResponse:
    global_missing = []
    if not settings.gemini_intent_api_key:
        global_missing.append("GEMINI_INTENT_API_KEY")
    return ProvidersResponse(
        providers=[adapter.info() for adapter in provider_registry.values()],
        global_missing_config=global_missing,
    )


def _build_benchmark_pipeline(
    settings: Settings,
    provider_registry,
) -> BenchmarkPipeline:
    intent_client = (
        GeminiIntentClient(
            GeminiClient(
                settings.gemini_intent_api_key,
                settings.gemini_intent_model,
            )
        )
        if settings.gemini_intent_api_key
        else MissingGeminiRoleClient("GEMINI_INTENT_API_KEY")
    )
    analysis_client = (
        GeminiAnalysisClient(
            GeminiClient(
                settings.gemini_analysis_api_key,
                settings.gemini_analysis_model,
            )
        )
        if settings.gemini_analysis_api_key
        else MissingGeminiRoleClient("GEMINI_ANALYSIS_API_KEY")
    )
    return BenchmarkPipeline(
        intent_client,
        analysis_client,
        provider_registry,
        settings,
    )


def _build_prototype_orchestrator(
    settings: Settings,
    store: PrototypeStore,
) -> PrototypeResearchOrchestrator:
    intent_client = (
        GeminiIntentClient(
            GeminiClient(
                settings.gemini_intent_api_key,
                settings.gemini_intent_model,
            )
        )
        if settings.gemini_intent_api_key
        else MissingGeminiRoleClient("GEMINI_INTENT_API_KEY")
    )
    analysis_client = (
        GeminiAnalysisClient(
            GeminiClient(
                settings.gemini_analysis_api_key,
                settings.gemini_analysis_model,
            )
        )
        if settings.gemini_analysis_api_key
        else MissingGeminiRoleClient("GEMINI_ANALYSIS_API_KEY")
    )
    return PrototypeResearchOrchestrator(
        intent_client=intent_client,
        analysis_client=analysis_client,
        providers=[
            FirecrawlAdapter(settings),
            TavilyAdapter(settings),
            ExaAdapter(settings),
        ],
        store=store,
    )


def _build_pipeline(settings: Settings) -> ProductAnalysisPipeline:
    gemini_client = GeminiClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
    )
    gemini_search_client = GeminiSearchClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
    )
    return ProductAnalysisPipeline(
        intent_classifier=IntentClassifierAgent(gemini_client=gemini_client),
        market_research_agent=GeminiTunisiaResearchAgent(
            gemini_search_client=gemini_search_client,
        ),
        china_supplier_research_agent=GeminiChinaSupplierResearchAgent(
            gemini_search_client=gemini_search_client,
        ),
        timeout_seconds=settings.analysis_timeout_seconds,
    )


def _build_pipeline_or_none(
    settings: Settings,
) -> ProductAnalysisPipeline | None:
    if not settings.gemini_api_key:
        return None
    return _build_pipeline(settings)


app = create_app()
