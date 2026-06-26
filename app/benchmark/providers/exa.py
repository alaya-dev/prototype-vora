from __future__ import annotations

import httpx

from app.benchmark.providers.base import (
    ProviderAdapterError,
    ProviderConfigRequirement,
    SearchProviderAdapter,
    analysis_requirement,
    new_http_client,
)
from app.benchmark.query_strategy import build_regional_queries
from app.benchmark.schemas import ProviderEvidence, ProviderRawSource


class ExaAdapter(SearchProviderAdapter):
    provider_id = "exa"
    provider_name = "Exa + Gemini"
    requires_gemini_analysis = True
    production_risk = "medium"
    cost_notes = (
        "Uses one Exa search/content request per raw search query plus one Gemini "
        "analysis call when evidence is found. Pricing and free tiers may change."
    )

    def __init__(self, settings):
        super().__init__(settings)
        self._client_factory = new_http_client

    def requirements(self):
        return [
            ProviderConfigRequirement("EXA_API_KEY", self.settings.exa_api_key),
            analysis_requirement(self.settings),
        ]

    async def search(self, product: str) -> ProviderEvidence:
        self._raise_if_not_configured()
        queries = build_regional_queries(product, self.settings.search_queries_per_region)
        sources: list[ProviderRawSource] = []
        api_calls = 0
        try:
            async with self._client_factory() as client:
                for region, query_list in (
                    ("tunisia", queries.tunisia),
                    ("china", queries.china),
                ):
                    for query in query_list:
                        response = await client.post(
                            "https://api.exa.ai/search",
                            headers={
                                "x-api-key": self.settings.exa_api_key,
                                "Content-Type": "application/json",
                            },
                            json={
                                "query": query,
                                "numResults": self.settings.search_results_per_query,
                                "contents": {"text": True},
                            },
                        )
                        api_calls += 1
                        response.raise_for_status()
                        for item in response.json().get("results", []):
                            text = item.get("text", "") or ""
                            sources.append(
                                ProviderRawSource(
                                    title=item.get("title", ""),
                                    url=item.get("url", ""),
                                    snippet=item.get("summary", "") or text[:300],
                                    content=text or None,
                                    region_hint=region,
                                    source_type="search_result",
                                )
                            )
        except httpx.HTTPError as error:
            raise ProviderAdapterError(f"{self.provider_name} request failed.") from error
        except (KeyError, ValueError, TypeError) as error:
            raise ProviderAdapterError(
                f"{self.provider_name} returned an unexpected response shape."
            ) from error

        return ProviderEvidence(
            provider_id=self.provider_id,
            sources=sources[: self.settings.max_raw_sources_per_provider],
            raw_queries_count=queries.total_count,
            provider_api_calls=api_calls,
        )
