from __future__ import annotations

from typing import TypeVar
import asyncio

from pydantic import BaseModel, ValidationError

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover - exercised only when dependency is missing
    genai = None
    types = None


T = TypeVar("T", bound=BaseModel)


class GeminiClientError(RuntimeError):
    """Raised when Gemini cannot produce a valid structured response."""


class GeminiClient:
    def __init__(self, api_key: str, model: str) -> None:
        if genai is None or types is None:
            raise GeminiClientError(
                "google-genai is not installed. Install requirements before running the API."
            )
        self.model = model
        self._client = genai.Client(api_key=api_key)

    async def generate_json(self, prompt: str, response_model: type[T]) -> T:
        primary_error: Exception | None = None
        for attempt in range(2):
            attempt_prompt = prompt
            if attempt == 1:
                attempt_prompt = (
                    f"{prompt}\n\n"
                    "Return only valid JSON that matches the provided schema exactly. "
                    "Do not include markdown, commentary, or omitted required fields."
                )

            try:
                response = await self._client.aio.models.generate_content(
                    model=self.model,
                    contents=attempt_prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        response_mime_type="application/json",
                        response_schema=_build_gemini_response_schema(response_model),
                    ),
                )
                return _coerce_model_response(response, response_model)
            except (ValidationError, ValueError, AttributeError, TypeError) as error:
                primary_error = error
                continue
            except Exception as error:  # pragma: no cover - depends on remote client behavior
                if _is_retryable_gemini_error(error) and attempt == 0:
                    await asyncio.sleep(1)
                    continue
                raise GeminiClientError(_build_gemini_error_message(error)) from error

        raise GeminiClientError(
            "Gemini returned invalid JSON twice."
        ) from primary_error


def _coerce_model_response(response, response_model: type[T]) -> T:
    parsed_response = getattr(response, "parsed", None)
    if isinstance(parsed_response, response_model):
        return parsed_response
    if isinstance(parsed_response, BaseModel):
        return response_model.model_validate(parsed_response.model_dump())
    if parsed_response is not None:
        return response_model.model_validate(parsed_response)

    raw_text = getattr(response, "text", "") or ""
    if not raw_text:
        raise ValueError("Gemini response did not include parsed JSON or text.")
    return response_model.model_validate_json(raw_text)


def _build_gemini_response_schema(response_model: type[T]) -> dict:
    return _strip_unsupported_schema_keys(response_model.model_json_schema())


def _strip_unsupported_schema_keys(value):
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if key == "additionalProperties":
                continue
            sanitized[key] = _strip_unsupported_schema_keys(item)
        return sanitized
    if isinstance(value, list):
        return [_strip_unsupported_schema_keys(item) for item in value]
    return value


def _is_retryable_gemini_error(error: Exception) -> bool:
    status_code = _extract_gemini_status_code(error)
    if status_code == 429 and _is_daily_quota_error(error):
        return False
    return status_code in {429, 500, 503}


def _build_gemini_error_message(error: Exception) -> str:
    status_code = _extract_gemini_status_code(error)
    if status_code == 503:
        return "Gemini is temporarily unavailable (503 high demand). Please retry in a moment."
    if status_code == 429:
        if _is_daily_quota_error(error):
            return (
                "Gemini daily free-tier quota is exhausted. "
                "Wait for the quota reset or enable billing for the Gemini API project."
            )
        return "Gemini rate limit reached (429). Please retry in a moment."
    if status_code == 400:
        return f"Gemini rejected the request (400): {error}"
    return f"Gemini request failed: {error}"


def _extract_gemini_status_code(error: Exception) -> int | None:
    for attribute_name in ("status_code", "code"):
        value = getattr(error, attribute_name, None)
        if isinstance(value, int):
            return value
    message = str(error)
    for status_code in (429, 500, 503, 400):
        if f"{status_code} " in message or f"{status_code}." in message:
            return status_code
    return None


def _is_daily_quota_error(error: Exception) -> bool:
    message = str(error).lower()
    daily_quota_markers = (
        "generaterequestsperdayperprojectpermodel",
        "free_tier_requests",
        "perday",
    )
    return any(marker in message for marker in daily_quota_markers)
