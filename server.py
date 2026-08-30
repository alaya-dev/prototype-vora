from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

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
from app.prototype.auth import (
    AuthAccount,
    AuthMeResponse,
    AuthUnauthenticatedResponse,
    LoginRequest,
    LoginResponse,
    PrototypeAuthService,
)
from app.prototype.schemas import (
    AnalyticsRunDetail,
    AnalyticsRunSummary,
    AnalyticsSummary,
    CostConfig,
    PrototypeAnalyzeRequest,
    PrototypeAnalyzeResponse,
    PrototypePdfRequest,
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
    _extract_gemini_status_code,
)
from app.services.gemini_search_client import GeminiSearchClient, GeminiSearchClientError
from app.services.pdf_report import build_opportunity_pdf, opportunity_pdf_filename


logger = logging.getLogger(__name__)
ANALYSIS_TEMPORARILY_UNAVAILABLE = {
    "code": "ANALYSIS_TEMPORARILY_UNAVAILABLE",
    "message": "Analysis is temporarily taking longer than expected. Please retry in a few moments.",
}


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
    intent_client, analysis_client = _build_gemini_role_clients(resolved_settings)
    resolved_benchmark_pipeline = benchmark_pipeline or _build_benchmark_pipeline(
        resolved_settings,
        provider_registry,
        intent_client,
        analysis_client,
    )
    resolved_pipeline = pipeline or _build_pipeline_or_none(resolved_settings)
    resolved_store = prototype_store or PrototypeStore(resolved_settings.prototype_db_path)
    auth_service = PrototypeAuthService(resolved_settings, resolved_store)
    resolved_prototype_orchestrator = prototype_orchestrator or _build_prototype_orchestrator(
        resolved_settings,
        resolved_store,
        intent_client,
        analysis_client,
    )

    app = FastAPI(title="VORA API", version="2.0.0")
    app.add_middleware(
        SessionMiddleware,
        secret_key=resolved_settings.session_secret or "prototype-development-only-session-secret",
        session_cookie="nexora_session",
        max_age=resolved_settings.session_max_age_seconds,
        same_site="lax",
        https_only=resolved_settings.session_cookie_secure,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def require_admin_password(x_admin_password: str | None = Header(default=None)) -> None:
        expected = resolved_settings.admin_dashboard_password
        if expected and x_admin_password != expected:
            raise HTTPException(status_code=401, detail="Analytics password required.")

    def require_auth_configuration() -> None:
        if not auth_service.configured:
            raise HTTPException(status_code=503, detail="Authentication configuration is unavailable.")

    def require_authenticated_user(request: Request) -> AuthAccount:
        email = request.session.get("email")
        if not email:
            request.session.clear()
            raise HTTPException(status_code=401, detail="Authentication required.")
        require_auth_configuration()
        account = auth_service.account_for_email(email)
        if account is None:
            request.session.clear()
            raise HTTPException(status_code=401, detail="Authentication required.")
        return account

    @app.get("/health")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/auth/login", response_model=LoginResponse)
    async def auth_login(payload: LoginRequest, request: Request) -> LoginResponse:
        require_auth_configuration()
        account = auth_service.authenticate(payload.email, payload.password)
        if account is None:
            raise HTTPException(status_code=401, detail="Email ou mot de passe invalide.")
        request.session.clear()
        request.session["email"] = account.email
        return LoginResponse()

    @app.get("/auth/me", response_model=AuthMeResponse | AuthUnauthenticatedResponse)
    async def auth_me(request: Request) -> AuthMeResponse | AuthUnauthenticatedResponse:
        email = request.session.get("email")
        if not email or not auth_service.configured:
            request.session.clear()
            return AuthUnauthenticatedResponse()
        account = auth_service.account_for_email(email)
        if account is None:
            request.session.clear()
            return AuthUnauthenticatedResponse()
        return auth_service.profile(account)

    @app.post("/auth/logout")
    async def auth_logout(request: Request) -> dict[str, bool]:
        request.session.clear()
        return {"authenticated": False}

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
        except (GeminiClientError, RuntimeError) as error:
            _log_analysis_failure(error)
            raise HTTPException(status_code=503, detail=ANALYSIS_TEMPORARILY_UNAVAILABLE) from error

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
        account: AuthAccount = Depends(require_authenticated_user),
    ) -> PrototypeAnalyzeResponse | JSONResponse:
        reservation_id = auth_service.reserve_analysis(account)
        if reservation_id is None:
            return JSONResponse(
                status_code=403,
                content={
                    "code": "ANALYSIS_QUOTA_EXHAUSTED",
                    "message": "Votre quota de 3 analyses est épuisé.",
                },
            )
        try:
            resolved_prototype_orchestrator.cost_config = resolved_store.get_cost_config()
            response = await resolved_prototype_orchestrator.analyze(request)
        except (GeminiClientError, GeminiSearchClientError) as error:
            auth_service.release_analysis(reservation_id)
            _log_analysis_failure(error)
            raise HTTPException(status_code=503, detail=ANALYSIS_TEMPORARILY_UNAVAILABLE) from error
        except RuntimeError as error:
            auth_service.release_analysis(reservation_id)
            _log_analysis_failure(error)
            raise HTTPException(status_code=503, detail=ANALYSIS_TEMPORARILY_UNAVAILABLE) from error
        except Exception:
            auth_service.release_analysis(reservation_id)
            raise
        auth_service.confirm_analysis(reservation_id)
        return response

    @app.get("/prototype/runs/{run_id}/reveal", response_model=PrototypeRevealResponse)
    async def prototype_reveal(
        run_id: str,
        _: AuthAccount = Depends(require_authenticated_user),
    ) -> PrototypeRevealResponse:
        try:
            return await resolved_prototype_orchestrator.reveal(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Prototype run not found.") from error

    @app.post("/prototype/runs/{run_id}/pdf")
    async def prototype_pdf(
        run_id: str,
        request: PrototypePdfRequest,
        _: AuthAccount = Depends(require_authenticated_user),
    ) -> Response:
        if request.report.run_id != run_id:
            raise HTTPException(status_code=400, detail="PDF report does not match the requested run.")
        try:
            pdf_bytes = build_opportunity_pdf(request.report, "fr")
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=500, detail="PDF generation failed.") from error
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{opportunity_pdf_filename(request.report)}"',
            },
        )

    @app.get("/api/analytics/runs", response_model=list[AnalyticsRunSummary])
    async def analytics_runs(_: None = Depends(require_admin_password)) -> list[AnalyticsRunSummary]:
        return resolved_store.list_runs()

    @app.get("/api/analytics/runs/{run_id}", response_model=AnalyticsRunDetail)
    async def analytics_run_detail(
        run_id: str,
        _: None = Depends(require_admin_password),
    ) -> AnalyticsRunDetail:
        try:
            return resolved_store.get_run_detail(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Prototype run not found.") from error

    @app.get("/api/analytics/summary", response_model=AnalyticsSummary)
    async def analytics_summary(_: None = Depends(require_admin_password)) -> AnalyticsSummary:
        return resolved_store.get_summary()

    @app.get("/api/analytics/cost-config", response_model=CostConfig)
    async def get_cost_config(_: None = Depends(require_admin_password)) -> CostConfig:
        return resolved_store.get_cost_config()

    @app.post("/api/analytics/cost-config", response_model=CostConfig)
    async def save_cost_config(
        config: CostConfig,
        _: None = Depends(require_admin_password),
    ) -> CostConfig:
        saved = resolved_store.save_cost_config(config)
        resolved_prototype_orchestrator.cost_config = saved
        return saved

    @app.get("/api/sourcing-agents", response_model=list[SourcingAgent])
    async def list_sourcing_agents(
        active_only: bool = False,
        _: None = Depends(require_admin_password),
    ) -> list[SourcingAgent]:
        return resolved_store.list_sourcing_agents(active_only=active_only)

    @app.post("/api/sourcing-agents", response_model=SourcingAgent)
    async def create_sourcing_agent(
        agent: SourcingAgent,
        _: None = Depends(require_admin_password),
    ) -> SourcingAgent:
        agent_id = resolved_store.upsert_sourcing_agent(agent.model_dump(exclude={"id"}))
        return resolved_store.list_sourcing_agents(active_only=False)[-1].model_copy(update={"id": agent_id})

    @app.put("/api/sourcing-agents/{agent_id}", response_model=SourcingAgent)
    async def update_sourcing_agent(
        agent_id: int,
        agent: SourcingAgent,
        _: None = Depends(require_admin_password),
    ) -> SourcingAgent:
        resolved_store.upsert_sourcing_agent(agent.model_dump(exclude={"id"}), agent_id=agent_id)
        for item in resolved_store.list_sourcing_agents(active_only=False):
            if item.id == agent_id:
                return item
        raise HTTPException(status_code=404, detail="Sourcing agent not found.")

    @app.delete("/api/sourcing-agents/{agent_id}")
    async def delete_sourcing_agent(
        agent_id: int,
        _: None = Depends(require_admin_password),
    ) -> dict[str, bool]:
        resolved_store.delete_sourcing_agent(agent_id)
        return {"deleted": True}

    @app.get("/analytics", response_class=HTMLResponse)
    async def analytics_page() -> str:
        with open("static/index.html", "r", encoding="utf-8") as file:
            return file.read()

    app.mount("/logo", StaticFiles(directory="logo"), name="logo")
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
    return app


class MissingGeminiRoleClient:
    def __init__(self, variable_name: str) -> None:
        self.variable_name = variable_name

    async def classify(self, product: str):
        raise GeminiClientError("Gemini intent configuration is unavailable.")

    async def extract(self, product: str, evidence):
        raise GeminiClientError("Gemini analysis configuration is unavailable.")

    async def extract_client_analysis(self, product, evidence, cost_config, quantity_scenarios):
        raise GeminiClientError("Gemini analysis configuration is unavailable.")


def _build_provider_infos(
    settings: Settings,
    provider_registry,
) -> ProvidersResponse:
    global_missing = []
    if not settings.gemini_intent_api_key:
        global_missing.append("GEMINI_INTENT_API_KEY")
    if not settings.gemini_analysis_api_key:
        global_missing.append("GEMINI_ANALYSIS_API_KEY")
    return ProvidersResponse(
        providers=[adapter.info() for adapter in provider_registry.values()],
        global_missing_config=global_missing,
    )


def _build_benchmark_pipeline(
    settings: Settings,
    provider_registry,
    intent_client=None,
    analysis_client=None,
) -> BenchmarkPipeline:
    if intent_client is None or analysis_client is None:
        intent_client, analysis_client = _build_gemini_role_clients(settings)
    return BenchmarkPipeline(
        intent_client,
        analysis_client,
        provider_registry,
        settings,
    )


def _build_prototype_orchestrator(
    settings: Settings,
    store: PrototypeStore,
    intent_client=None,
    analysis_client=None,
) -> PrototypeResearchOrchestrator:
    if intent_client is None or analysis_client is None:
        intent_client, analysis_client = _build_gemini_role_clients(settings)
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


def _build_gemini_role_clients(settings: Settings):
    intent_client = (
        GeminiIntentClient(GeminiClient(settings.gemini_intent_api_key, settings.gemini_intent_model))
        if settings.gemini_intent_api_key
        else MissingGeminiRoleClient("GEMINI_INTENT_API_KEY")
    )
    analysis_client = (
        GeminiAnalysisClient(GeminiClient(settings.gemini_analysis_api_key, settings.gemini_analysis_model))
        if settings.gemini_analysis_api_key
        else MissingGeminiRoleClient("GEMINI_ANALYSIS_API_KEY")
    )
    return intent_client, analysis_client


def _log_analysis_failure(error: Exception) -> None:
    logger.warning(
        "Client analysis did not complete exception_type=%s provider_http_code=%s.",
        error.__class__.__name__,
        _extract_gemini_status_code(error),
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
