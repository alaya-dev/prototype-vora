from __future__ import annotations

import asyncio
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import bcrypt
from fastapi.testclient import TestClient

from app.config import Settings
from app.prototype.schemas import PrototypeAnalyzeResponse
from app.prototype.storage import PrototypeStore
from app.services.gemini_client import GeminiClientError
from server import create_app


TEST_PASSWORD = "test-only-password"
TEST_HASH = bcrypt.hashpw(TEST_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


class SuccessfulPrototype:
    def __init__(self) -> None:
        self.calls = 0
        self.cost_config = None

    async def analyze(self, _request) -> PrototypeAnalyzeResponse:
        self.calls += 1
        return PrototypeAnalyzeResponse(run_id=f"run_{self.calls}")


class FailingPrototype:
    cost_config = None

    async def analyze(self, _request) -> PrototypeAnalyzeResponse:
        raise GeminiClientError("provider unavailable")


class PrototypeAuthTests(unittest.TestCase):
    def test_password_hash_accepts_only_the_correct_password(self) -> None:
        client = self._client()
        self.assertEqual(client.post("/auth/login", json={"email": "info@stt.tn", "password": TEST_PASSWORD}).status_code, 200)
        self.assertEqual(client.post("/auth/login", json={"email": "info@stt.tn", "password": "wrong"}).status_code, 401)

    def test_cookie_has_secure_session_flags(self) -> None:
        client = self._client(cookie_secure=True)
        response = client.post("/auth/login", json={"email": "info@stt.tn", "password": TEST_PASSWORD})
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=lax", cookie)
        self.assertIn("secure", cookie)

    def test_unauthenticated_analyze_is_rejected(self) -> None:
        client = self._client()
        response = client.post("/prototype/analyze", json={"product": "T9", "market": "Tunisia", "sourcing_country": "China"})
        self.assertEqual(response.status_code, 401)

    def test_client_quota_and_accounts_are_independent(self) -> None:
        prototype = SuccessfulPrototype()
        client = self._client(prototype=prototype)
        self._login(client, "info@stt.tn")
        for _ in range(3):
            self.assertEqual(self._analyze(client).status_code, 200)
        self.assertEqual(client.get("/auth/me").json()["quota_remaining"], 0)
        exhausted = self._analyze(client)
        self.assertEqual(exhausted.status_code, 403)
        self.assertEqual(exhausted.json()["code"], "ANALYSIS_QUOTA_EXHAUSTED")

        client.post("/auth/logout")
        self._login(client, "vizyaconsulting@gmail.com")
        profile = client.get("/auth/me").json()
        self.assertEqual(profile["quota_used"], 0)
        self.assertEqual(profile["quota_remaining"], 3)
        for _ in range(3):
            self.assertEqual(self._analyze(client).status_code, 200)
        self.assertEqual(self._analyze(client).status_code, 403)

    def test_invalid_request_does_not_consume_quota(self) -> None:
        client = self._client()
        self._login(client, "info@stt.tn")
        invalid = client.post(
            "/prototype/analyze",
            json={"product": "T9", "market": "Tunisia", "sourcing_country": "China", "invalid": True},
        )
        self.assertEqual(invalid.status_code, 422)
        profile = client.get("/auth/me").json()
        self.assertEqual(profile["quota_used"], 0)
        self.assertEqual(profile["quota_remaining"], 3)

    def test_admin_is_unlimited(self) -> None:
        prototype = SuccessfulPrototype()
        client = self._client(prototype=prototype)
        self._login(client, "admin@gmail.com")
        for _ in range(5):
            self.assertEqual(self._analyze(client).status_code, 200)
        profile = client.get("/auth/me").json()
        self.assertTrue(profile["unlimited"])
        self.assertIsNone(profile["quota_remaining"])
        self.assertEqual(prototype.calls, 5)

    def test_failed_analysis_releases_reserved_quota(self) -> None:
        client = self._client(prototype=FailingPrototype())
        self._login(client, "info@stt.tn")
        self.assertEqual(self._analyze(client).status_code, 503)
        profile = client.get("/auth/me").json()
        self.assertEqual(profile["quota_used"], 0)
        self.assertEqual(profile["quota_remaining"], 3)

    def test_atomic_reservation_allows_only_one_final_slot(self) -> None:
        store = PrototypeStore(self._temp_db())
        store.ensure_auth_quota_account("info@stt.tn")
        for _ in range(2):
            reservation = store.reserve_auth_quota("info@stt.tn")
            self.assertIsNotNone(reservation)
            store.confirm_auth_quota_reservation(reservation or "")
        with ThreadPoolExecutor(max_workers=2) as executor:
            reservations = list(executor.map(lambda _: store.reserve_auth_quota("info@stt.tn"), range(2)))
        self.assertEqual(sum(item is not None for item in reservations), 1)
        for reservation in reservations:
            if reservation:
                store.release_auth_quota_reservation(reservation)

    def test_logout_invalidates_session_and_expired_cookie_is_rejected(self) -> None:
        client = self._client(session_max_age_seconds=1)
        self._login(client, "info@stt.tn")
        self.assertEqual(client.get("/auth/me").status_code, 200)
        with patch("itsdangerous.timed.time.time", return_value=9_999_999_999):
            expired = client.get("/auth/me")
            self.assertEqual(expired.status_code, 200)
            self.assertFalse(expired.json()["authenticated"])
        self._login(client, "info@stt.tn")
        self.assertEqual(client.post("/auth/logout").status_code, 200)
        self.assertFalse(client.get("/auth/me").json()["authenticated"])

    def _client(
        self,
        prototype: SuccessfulPrototype | FailingPrototype | None = None,
        cookie_secure: bool = False,
        session_max_age_seconds: int = 43_200,
    ) -> TestClient:
        return TestClient(
            create_app(
                settings=Settings(
                    gemini_api_key="",
                    gemini_model="",
                    analysis_timeout_seconds=45,
                    nexora_user1_email="info@stt.tn",
                    nexora_user1_password_hash=TEST_HASH,
                    nexora_user2_email="vizyaconsulting@gmail.com",
                    nexora_user2_password_hash=TEST_HASH,
                    nexora_admin_email="admin@gmail.com",
                    nexora_admin_password_hash=TEST_HASH,
                    session_secret="test-session-secret",
                    session_cookie_secure=cookie_secure,
                    session_max_age_seconds=session_max_age_seconds,
                ),
                prototype_store=PrototypeStore(self._temp_db()),
                prototype_orchestrator=prototype or SuccessfulPrototype(),
            )
        )

    @staticmethod
    def _login(client: TestClient, email: str) -> None:
        response = client.post("/auth/login", json={"email": email, "password": TEST_PASSWORD})
        assert response.status_code == 200

    @staticmethod
    def _analyze(client: TestClient):
        return client.post("/prototype/analyze", json={"product": "T9", "market": "Tunisia", "sourcing_country": "China"})

    @staticmethod
    def _temp_db() -> str:
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        return handle.name
