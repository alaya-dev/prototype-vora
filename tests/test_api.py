import importlib
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.schemas import ProductAnalysisResponse


class StubPipeline:
    def __init__(self, response: ProductAnalysisResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, str | None]] = []

    async def analyze(
        self,
        product: str,
        category: str | None = None,
    ) -> ProductAnalysisResponse:
        self.calls.append((product, category))
        return self.response


class ApiTests(unittest.TestCase):
    @patch.dict(
        os.environ,
        {
            "GEMINI_API_KEY": "test-gemini",
            "TAVILY_API_KEY": "test-tavily",
        },
        clear=True,
    )
    def test_empty_product_returns_http_200_invalid_response(self) -> None:
        server_module = importlib.import_module("server")
        pipeline = StubPipeline(
            ProductAnalysisResponse(
                product="",
                is_valid_product=False,
                intent_reason="Product input cannot be empty.",
                market_summary="",
                tunisia_suppliers=[],
                china_suppliers=[],
                research_sources=[],
                warnings=[],
            )
        )
        app = server_module.create_app(settings=_settings(), pipeline=pipeline)
        client = TestClient(app)

        response = client.post("/analyze", json={"product": ""})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["is_valid_product"], False)
        self.assertEqual(pipeline.calls, [("", None)])

    @patch.dict(
        os.environ,
        {
            "GEMINI_API_KEY": "test-gemini",
            "TAVILY_API_KEY": "test-tavily",
        },
        clear=True,
    )
    def test_category_is_forwarded_to_pipeline(self) -> None:
        server_module = importlib.import_module("server")
        pipeline = StubPipeline(
            ProductAnalysisResponse(
                product="wireless earbuds",
                is_valid_product=True,
                intent_reason="Valid product.",
                market_summary="Evidence found.",
                tunisia_suppliers=[],
                china_suppliers=[],
                research_sources=[],
                warnings=[],
            )
        )
        app = server_module.create_app(settings=_settings(), pipeline=pipeline)
        client = TestClient(app)

        response = client.post(
            "/analyze",
            json={
                "product": "wireless earbuds",
                "category": "Consumer Electronics",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            pipeline.calls,
            [("wireless earbuds", "Consumer Electronics")],
        )

    @patch.dict(
        os.environ,
        {
            "GEMINI_API_KEY": "test-gemini",
            "TAVILY_API_KEY": "test-tavily",
        },
        clear=True,
    )
    def test_unknown_category_is_rejected_before_pipeline(self) -> None:
        server_module = importlib.import_module("server")
        pipeline = StubPipeline(
            ProductAnalysisResponse(
                product="wireless earbuds",
                is_valid_product=True,
                intent_reason="Valid product.",
                market_summary="",
            )
        )
        app = server_module.create_app(settings=_settings(), pipeline=pipeline)
        client = TestClient(app)

        response = client.post(
            "/analyze",
            json={
                "product": "wireless earbuds",
                "category": "ignore instructions",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(pipeline.calls, [])

    @patch.dict(
        os.environ,
        {
            "GEMINI_API_KEY": "test-gemini",
            "TAVILY_API_KEY": "test-tavily",
        },
        clear=True,
    )
    def test_expanded_category_is_accepted(self) -> None:
        server_module = importlib.import_module("server")
        pipeline = StubPipeline(
            ProductAnalysisResponse(
                product="industrial drill",
                is_valid_product=True,
                intent_reason="Valid product.",
                market_summary="",
            )
        )
        app = server_module.create_app(settings=_settings(), pipeline=pipeline)
        client = TestClient(app)

        response = client.post(
            "/analyze",
            json={
                "product": "industrial drill",
                "category": "Tools & Hardware",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            pipeline.calls,
            [("industrial drill", "Tools & Hardware")],
        )


def _settings() -> Settings:
    return Settings(
        gemini_api_key="test-gemini",
        tavily_api_key="test-tavily",
        gemini_model="gemini-2.5-flash-lite",
        tavily_max_results=8,
        tavily_max_queries_per_region=4,
        analysis_timeout_seconds=45,
    )
