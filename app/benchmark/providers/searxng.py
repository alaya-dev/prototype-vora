from __future__ import annotations

import httpx

from app.benchmark.providers.base import (
    cap_sources_balanced,
    can_stop_after_source_cap,
    prioritized_query_groups,
    ProviderAdapterError,
    ProviderConfigRequirement,
    SearchProviderAdapter,
    analysis_requirement,
    new_http_client,
)
from app.benchmark.schemas import ProviderEvidence, ProviderRawSource


class SearXNGAdapter(SearchProviderAdapter):
    provider_id = "searxng"
    provider_name = "SearXNG + Gemini"
    requires_gemini_analysis = True
    production_risk = "high"
    cost_notes = (
        "Uses one SearXNG request per raw search query plus one Gemini analysis call "
        "when evidence is found. Reliability depends on the configured instance."
    )

    def __init__(self, settings):
        super().__init__(settings)
        self._client_factory = new_http_client

    def requirements(self):
        return [
            ProviderConfigRequirement(
                "SEARXNG_BASE_URL",
                self.settings.searxng_base_url,
            ),
            analysis_requirement(self.settings),
        ]

    async def search(self, product: str) -> ProviderEvidence:
        self._raise_if_not_configured()
        query_groups = prioritized_query_groups(product, self.settings)
        sources: list[ProviderRawSource] = []
        api_calls = 0
        base_url = self.settings.searxng_base_url.rstrip("/")
        try:
            async with self._client_factory() as client:
                for region, query_list in query_groups:
                    for query in query_list:
                        response = await client.get(
                            f"{base_url}/search",
                            params={
                                "q": query,
                                "format": "json",
                                "categories": "general",
                            },
                        )
                        api_calls += 1
                        response.raise_for_status()
                        for item in response.json().get("results", []):
                            sources.append(
                                ProviderRawSource(
                                    title=item.get("title", ""),
                                    url=item.get("url", ""),
                                    snippet=item.get("content", ""),
                                    region_hint=region,
                                    source_type="search_result",
                                )
                            )
                        if can_stop_after_source_cap(sources, self.settings):
                            break
                    if can_stop_after_source_cap(sources, self.settings):
                        break
        except httpx.HTTPError as error:
            raise ProviderAdapterError(f"{self.provider_name} request failed.") from error
        except (KeyError, ValueError, TypeError) as error:
            raise ProviderAdapterError(
                f"{self.provider_name} returned an unexpected response shape."
            ) from error

        return ProviderEvidence(
            provider_id=self.provider_id,
            sources=cap_sources_balanced(
                sources,
                self.settings.max_raw_sources_per_provider,
            ),
            raw_queries_count=api_calls,
            provider_api_calls=api_calls,
        )
