from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar
import asyncio

from pydantic import BaseModel, ValidationError

from app.services.gemini_client import (
    _build_gemini_error_message,
    _is_retryable_gemini_error,
)

try:
    from google import genai
except ImportError:  # pragma: no cover - exercised only when dependency is missing
    genai = None


T = TypeVar("T", bound=BaseModel)


class GeminiSearchClientError(RuntimeError):
    """Raised when grounded Gemini research cannot produce a valid response."""


@dataclass(frozen=True)
class GroundingCitation:
    title: str
    url: str


@dataclass(frozen=True)
class GroundedResponse(Generic[T]):
    payload: T
    citations: list[GroundingCitation]


class GeminiSearchClient:
    def __init__(self, api_key: str, model: str) -> None:
        if genai is None:
            raise GeminiSearchClientError(
                "google-genai is not installed. Install requirements before running the API."
            )
        self.model = model
        self._client = genai.Client(api_key=api_key)

    async def generate_grounded_json(
        self,
        prompt: str,
        response_model: type[T],
    ) -> GroundedResponse[T]:
        parsing_error: Exception | None = None
        for attempt in range(2):
            interaction = await self._create_interaction(
                _prompt_for_attempt(prompt, attempt),
                response_model,
                attempt,
            )
            _require_search_call(interaction)
            output_text = _model_output_text(interaction)
            try:
                payload = response_model.model_validate_json(output_text)
            except (ValidationError, ValueError) as error:
                parsing_error = error
                continue
            return GroundedResponse(
                payload=payload,
                citations=_extract_citations(interaction),
            )

        raise GeminiSearchClientError(
            "Gemini Search grounding returned invalid JSON twice."
        ) from parsing_error

    async def _create_interaction(
        self,
        prompt: str,
        response_model: type[T],
        attempt: int,
    ):
        try:
            return await self._client.aio.interactions.create(
                model=self.model,
                input=prompt,
                tools=[{"type": "google_search"}],
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": response_model.model_json_schema(),
                },
                store=False,
            )
        except Exception as error:  # pragma: no cover - remote SDK boundary
            if _is_retryable_gemini_error(error) and attempt == 0:
                await asyncio.sleep(1)
                return await self._create_interaction(prompt, response_model, 1)
            raise GeminiSearchClientError(
                _build_gemini_error_message(error)
            ) from error


def _prompt_for_attempt(prompt: str, attempt: int) -> str:
    if attempt == 0:
        return prompt
    return (
        f"{prompt}\n\n"
        "Return only one valid JSON object matching the requested schema. "
        "Do not include markdown fences or commentary."
    )


def _require_search_call(interaction) -> None:
    if not any(
        getattr(step, "type", None) == "google_search_call"
        for step in getattr(interaction, "steps", [])
    ):
        raise GeminiSearchClientError(
            "Gemini research did not execute Google Search grounding."
        )


def _model_output_text(interaction) -> str:
    text_blocks = [
        getattr(content, "text", "")
        for step in getattr(interaction, "steps", [])
        if getattr(step, "type", None) == "model_output"
        for content in getattr(step, "content", [])
        if getattr(content, "type", None) == "text"
    ]
    output_text = "".join(text_blocks) or getattr(interaction, "output_text", "")
    if not output_text:
        raise GeminiSearchClientError(
            "Gemini Search grounding returned no model output."
        )
    return output_text


def _extract_citations(interaction) -> list[GroundingCitation]:
    citations_by_url: dict[str, GroundingCitation] = {}
    for step in getattr(interaction, "steps", []):
        if getattr(step, "type", None) != "model_output":
            continue
        for content in getattr(step, "content", []):
            for annotation in getattr(content, "annotations", []) or []:
                url = getattr(annotation, "url", "")
                if getattr(annotation, "type", None) != "url_citation" or not url:
                    continue
                citations_by_url.setdefault(
                    url,
                    GroundingCitation(
                        title=getattr(annotation, "title", "") or url,
                        url=url,
                    ),
                )
    return list(citations_by_url.values())
