import tempfile
import unittest
from types import SimpleNamespace

import bcrypt
from pydantic import BaseModel
from fastapi.testclient import TestClient

from app.config import Settings
from app.prototype.schemas import PrototypeAnalysisDraft
from app.prototype.storage import PrototypeStore
from app.services.gemini_client import GeminiClientError
from app.services.groq_client import GroqClient, GroqClientError
from app.services.groq_client import _normalize_client_analysis_payload


class Reply(BaseModel):
    status: str


class FakeRateLimitError(Exception):
    status_code = 429

    def __init__(self, retry_after: str | None = None) -> None:
        self.response = SimpleNamespace(headers={"retry-after": retry_after} if retry_after else {})


class FakeJsonValidationError(Exception):
    status_code = 400
    body = {"error": {"code": "json_validate_failed"}}


class FakeCompletions:
    def __init__(self, outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=outcome))]
        )


class FakeClient:
    def __init__(self, outcomes) -> None:
        self.completions = FakeCompletions(outcomes)
        self.chat = SimpleNamespace(completions=self.completions)


class GroqClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_structured_response_is_validated(self) -> None:
        client = FakeClient(['{"status":"ok"}'])
        groq = GroqClient("not-logged", "openai/gpt-oss-20b", client=client, jitter=lambda: 0)

        result = await groq.generate_json("Return status.", Reply)

        self.assertEqual(result.status, "ok")
        request = client.completions.calls[0]
        self.assertEqual(request["model"], "openai/gpt-oss-20b")
        self.assertEqual(request["response_format"], {"type": "json_object"})
        self.assertIn("valid JSON object", request["messages"][0]["content"])

    async def test_429_retries_once_and_honors_retry_after(self) -> None:
        sleeps = []

        async def sleep(seconds: float) -> None:
            sleeps.append(seconds)

        client = FakeClient([FakeRateLimitError("3"), '{"status":"ok"}'])
        groq = GroqClient("not-logged", "openai/gpt-oss-20b", client=client, sleep=sleep, jitter=lambda: 0)

        result = await groq.generate_json("Return status.", Reply)

        self.assertEqual(result.status, "ok")
        self.assertEqual(len(client.completions.calls), 2)
        self.assertEqual(sleeps, [3.0])

    async def test_429_after_all_attempts_is_normalized(self) -> None:
        sleeps = []

        async def sleep(seconds: float) -> None:
            sleeps.append(seconds)

        client = FakeClient([FakeRateLimitError(), FakeRateLimitError(), FakeRateLimitError()])
        groq = GroqClient("not-logged", "openai/gpt-oss-20b", client=client, sleep=sleep, jitter=lambda: 0)

        with self.assertRaises(GroqClientError) as context:
            await groq.generate_json("Return status.", Reply)

        self.assertEqual(str(context.exception), "Groq request could not be completed.")
        self.assertEqual(len(client.completions.calls), 3)
        self.assertEqual(sleeps, [2.0, 5.0])

    async def test_transient_json_validation_failure_retries(self) -> None:
        sleeps = []

        async def sleep(seconds: float) -> None:
            sleeps.append(seconds)

        client = FakeClient([FakeJsonValidationError(), '{"status":"ok"}'])
        groq = GroqClient("not-logged", "openai/gpt-oss-20b", client=client, sleep=sleep, jitter=lambda: 0)

        result = await groq.generate_json("Return status.", Reply)

        self.assertEqual(result.status, "ok")
        self.assertEqual(sleeps, [2.0])

    async def test_client_analysis_normalizes_known_legacy_shapes_before_strict_validation(self) -> None:
        client = FakeClient([
            '{"sourcing_summary":"Aucune offre fiable.",'
            '"retail_market_summary":"Aucune donnée fiable.",'
            '"tunisia_retail_market":{"seller_density":null},'
            '"profitability_estimate":{"source_unit_price_usd":null,"expected_units_sold":null,'
            '"margin_percent":null,"assumptions_and_risks":"Vérifier le fret."},'
            '"decision_scores":{"main_decision_factors":"Vérifier la concurrence."},'
            '"warnings":"Données limitées."}'
        ])
        groq = GroqClient("not-logged", "openai/gpt-oss-20b", client=client, jitter=lambda: 0)

        result = await groq.generate_json(
            "Return the client analysis.",
            PrototypeAnalysisDraft,
            payload_normalizer=_normalize_client_analysis_payload,
        )

        self.assertEqual(result.sourcing_summary.tunisia_wholesale_summary, "Aucune offre fiable.")
        self.assertEqual(result.retail_market_summary.availability_notes, "Aucune donnée fiable.")
        self.assertEqual(result.tunisia_retail_market.seller_density, "unknown")
        self.assertEqual(result.warnings, ["Données limitées."])
        self.assertEqual(result.profitability_estimate.assumptions, ["Vérifier le fret."])


class GroqApiErrorTests(unittest.TestCase):
    def test_prospect_api_hides_provider_details(self) -> None:
        import server

        class FailingPrototype:
            async def analyze(self, _request):
                raise GeminiClientError("429 rate_limit_exceeded secret-key")

        password = "test-only-password"
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db.close()
        app = server.create_app(
            settings=Settings(
                gemini_api_key="",
                gemini_model="",
                analysis_timeout_seconds=45,
                nexora_user1_email="info@stt.tn",
                nexora_user1_password_hash=password_hash,
                nexora_user2_email="vizyaconsulting@gmail.com",
                nexora_user2_password_hash=password_hash,
                nexora_admin_email="admin@gmail.com",
                nexora_admin_password_hash=password_hash,
                session_secret="test-session-secret",
            ),
            prototype_orchestrator=FailingPrototype(),
            prototype_store=PrototypeStore(db.name),
        )

        client = TestClient(app)
        self.assertEqual(
            client.post("/auth/login", json={"email": "info@stt.tn", "password": password}).status_code,
            200,
        )
        response = client.post(
            "/prototype/analyze",
            json={
                "product": "Huile moteur 5W-30 4L",
                "market": "Tunisia",
                "sourcing_country": "China",
            },
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "ANALYSIS_TEMPORARILY_UNAVAILABLE")
        self.assertNotIn("groq", response.text.lower())
        self.assertNotIn("429", response.text)
        self.assertNotIn("secret", response.text.lower())
