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


class SerperAdapter(SearchProviderAdapter):
    provider_id = "serper"
    provider_name = "Serper + Gemini"
    requires_gemini_analysis = True
    production_risk = "medium"
    cost_notes = (
        "Uses one Serper API request per raw search query plus one Gemini analysis call "
        "when evidence is found. Pricing and free tiers may change."
    )

    def __init__(self, settings):
        super().__init__(settings)
        self._client_factory = new_http_client

    def requirements(self):
        return [
            ProviderConfigRequirement("SERPER_API_KEY", self.settings.serper_api_key),
            analysis_requirement(self.settings),
        ]

    async def search(self, product: str) -> ProviderEvidence:
        self._raise_if_not_configured()
        query_groups = prioritized_query_groups(product, self.settings)
        sources: list[ProviderRawSource] = []
        api_calls = 0
        try:
            async with self._client_factory() as client:
                for region, query_list in query_groups:
                    for query in query_list:
                        response = await client.post(
                            "https://google.serper.dev/search",
                            headers={
                                "X-API-KEY": self.settings.serper_api_key,
                                "Content-Type": "application/json",
                            },
                            json={
                                "q": query,
                                "num": self.settings.search_results_per_query,
                            },
                        )
                        api_calls += 1
                        response.raise_for_status()
                        for item in response.json().get("organic", []):
                            sources.append(
                                ProviderRawSource(
                                    title=item.get("title", ""),
                                    url=item.get("link", ""),
                                    snippet=item.get("snippet", ""),
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
