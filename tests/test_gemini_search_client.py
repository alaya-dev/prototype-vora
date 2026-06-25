import json
from types import SimpleNamespace
import unittest

from app.schemas import StrictModel
from app.services.gemini_search_client import (
    GeminiSearchClient,
    GeminiSearchClientError,
)


class SamplePayload(StrictModel):
    answer: str


class RecordingInteractions:
    def __init__(self, interactions: list[SimpleNamespace]) -> None:
        self.interactions = interactions
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.interactions.pop(0)


def _interaction(
    output_text: str,
    *,
    include_search: bool = True,
    citations: list[tuple[str, str]] | None = None,
) -> SimpleNamespace:
    steps = []
    if include_search:
        steps.append(SimpleNamespace(type="google_search_call"))
    annotations = [
        SimpleNamespace(type="url_citation", title=title, url=url)
        for title, url in citations or []
    ]
    steps.append(
        SimpleNamespace(
            type="model_output",
            content=[
                SimpleNamespace(
                    type="text",
                    text=output_text,
                    annotations=annotations,
                )
            ],
        )
    )
    return SimpleNamespace(output_text=output_text, steps=steps)


class GeminiSearchClientTests(unittest.IsolatedAsyncioTestCase):
    def _client(self, interactions: list[SimpleNamespace]) -> tuple[
        GeminiSearchClient,
        RecordingInteractions,
    ]:
        endpoint = RecordingInteractions(interactions)
        sdk_client = SimpleNamespace(
            aio=SimpleNamespace(interactions=endpoint),
        )
        client = GeminiSearchClient(
            api_key="test-key",
            model="gemini-3.1-flash-lite",
        )
        client._client = sdk_client
        return client, endpoint

    async def test_grounded_request_uses_google_search_tool(self) -> None:
        client, endpoint = self._client(
            [_interaction('{"answer":"grounded"}')]
        )

        grounded = await client.generate_grounded_json(
            "Research this product.",
            SamplePayload,
        )

        self.assertEqual(grounded.payload.answer, "grounded")
        self.assertEqual(endpoint.calls[0]["tools"], [{"type": "google_search"}])
        self.assertNotIn("generation_config", endpoint.calls[0])
        self.assertFalse(endpoint.calls[0]["store"])
        self.assertNotIn("response_format", endpoint.calls[0])
        self.assertIn("Return only valid JSON", endpoint.calls[0]["input"])

    async def test_citations_are_deduplicated_in_first_seen_order(self) -> None:
        client, _endpoint = self._client(
            [
                _interaction(
                    '{"answer":"grounded"}',
                    citations=[
                        ("First", "https://example.com/one"),
                        ("Duplicate", "https://example.com/one"),
                        ("Second", "https://example.com/two"),
                    ],
                )
            ]
        )

        grounded = await client.generate_grounded_json(
            "Research this product.",
            SamplePayload,
        )

        self.assertEqual(
            [citation.url for citation in grounded.citations],
            ["https://example.com/one", "https://example.com/two"],
        )
        self.assertEqual(grounded.citations[0].title, "First")

    async def test_invalid_json_is_retried_once_with_stricter_prompt(self) -> None:
        client, endpoint = self._client(
            [
                _interaction("not json"),
                _interaction(json.dumps({"answer": "recovered"})),
            ]
        )

        grounded = await client.generate_grounded_json(
            "Research this product.",
            SamplePayload,
        )

        self.assertEqual(grounded.payload.answer, "recovered")
        self.assertEqual(len(endpoint.calls), 2)
        self.assertIn("Return only one valid JSON object", endpoint.calls[1]["input"])

    async def test_repeated_invalid_json_raises_clean_error(self) -> None:
        client, _endpoint = self._client(
            [_interaction("not json"), _interaction("still not json")]
        )

        with self.assertRaisesRegex(
            GeminiSearchClientError,
            "invalid JSON twice",
        ):
            await client.generate_grounded_json(
                "Research this product.",
                SamplePayload,
            )

    async def test_response_without_search_call_is_rejected(self) -> None:
        client, _endpoint = self._client(
            [
                _interaction('{"answer":"internal knowledge"}', include_search=False),
                _interaction('{"answer":"still internal"}', include_search=False),
            ]
        )

        with self.assertRaisesRegex(
            GeminiSearchClientError,
            "did not execute Google Search",
        ):
            await client.generate_grounded_json(
                "Research this product.",
                SamplePayload,
            )

    async def test_ungrounded_response_is_retried_with_mandatory_search_prompt(
        self,
    ) -> None:
        client, endpoint = self._client(
            [
                _interaction('{"answer":"internal knowledge"}', include_search=False),
                _interaction('{"answer":"grounded"}'),
            ]
        )

        grounded = await client.generate_grounded_json(
            "Research this product.",
            SamplePayload,
        )

        self.assertEqual(grounded.payload.answer, "grounded")
        self.assertEqual(len(endpoint.calls), 2)
        self.assertIn(
            "MUST execute Google Search",
            endpoint.calls[1]["input"],
        )
