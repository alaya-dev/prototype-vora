from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.agents.china_supplier_research import GeminiChinaSupplierResearchAgent
from app.agents.intent_classifier import IntentClassifierAgent
from app.agents.market_research import GeminiTunisiaResearchAgent
from app.config import Settings
from app.pipeline import PipelineError, PipelineTimeoutError, ProductAnalysisPipeline
from app.schemas import AnalyzeRequest, ProductAnalysisResponse
from app.services.gemini_client import GeminiClient, GeminiClientError
from app.services.gemini_search_client import GeminiSearchClient, GeminiSearchClientError


def create_app(
    settings: Settings | None = None,
    pipeline: ProductAnalysisPipeline | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    resolved_pipeline = pipeline or _build_pipeline(resolved_settings)

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

    @app.post("/analyze", response_model=ProductAnalysisResponse)
    async def analyze(request: AnalyzeRequest) -> ProductAnalysisResponse:
        try:
            return await resolved_pipeline.analyze(request.product, request.category)
        except PipelineTimeoutError as error:
            raise HTTPException(status_code=504, detail=str(error)) from error
        except (PipelineError, GeminiClientError, GeminiSearchClientError) as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    app.mount("/", StaticFiles(directory="static", html=True), name="static")
    return app


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


app = create_app()
