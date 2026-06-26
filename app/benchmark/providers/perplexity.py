from __future__ import annotations

import httpx

from app.benchmark.providers.base import (
    ProviderAdapterError,
    ProviderConfigRequirement,
    SearchProviderAdapter,
    new_http_client,
)
from app.benchmark.schemas import ProviderAnalysisResult, ProviderEvidence


class PerplexitySonarAdapter(SearchProviderAdapter):
    provider_id = "perplexity"
    provider_name = "Perplexity Sonar"
    requires_gemini_analysis = False
    production_risk = "medium"
    cost_notes = (
        "Uses one Perplexity Sonar request for direct web-grounded JSON output. "
        "Pricing and model behavior may change."
    )

    def __init__(self, settings):
        super().__init__(settings)
        self._client_factory = new_http_client

    def requirements(self):
        return [
            ProviderConfigRequirement(
                "PERPLEXITY_API_KEY",
                self.settings.perplexity_api_key,
            )
        ]

    async def search(self, product: str) -> ProviderEvidence:
        raise ProviderAdapterError(
            "Perplexity Sonar uses direct web-grounded analysis in this benchmark mode."
        )

    async def analyze_direct(self, product: str) -> ProviderAnalysisResult:
        self._raise_if_not_configured()
        prompt = (
            "Use web-grounded search to find sourcing evidence for this product. "
            "Return only strict JSON matching this schema: "
            f"{ProviderAnalysisResult.model_json_schema()}. "
            "Do not invent suppliers, prices, MOQ, stock, ratings, availability, or URLs. "
            f"Product: {product}"
        )
        try:
            async with self._client_factory() as client:
                response = await client.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.settings.perplexity_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "sonar",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise ProviderAdapterError(f"{self.provider_name} request failed.") from error
        except (KeyError, ValueError, TypeError) as error:
            raise ProviderAdapterError(
                f"{self.provider_name} returned an unexpected response shape."
            ) from error

        content = response.json()["choices"][0]["message"]["content"]
        try:
            return ProviderAnalysisResult.model_validate_json(content)
        except ValueError as error:
            raise ProviderAdapterError(
                f"{self.provider_name} returned invalid JSON."
            ) from error
