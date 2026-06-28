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


class DataForSEOAdapter(SearchProviderAdapter):
    provider_id = "dataforseo"
    provider_name = "DataForSEO + Gemini"
    requires_gemini_analysis = True
    production_risk = "medium"
    cost_notes = (
        "Uses one Google Organic Live Regular SERP request per raw search query plus "
        "one Gemini analysis call when evidence is found. Cost scales with SERP depth, "
        "so this adapter keeps to conservative generic regional queries first."
    )

    def __init__(self, settings):
        super().__init__(settings)
        self._client_factory = new_http_client

    def requirements(self):
        return [
            ProviderConfigRequirement(
                "DATAFORSEO_LOGIN",
                self.settings.dataforseo_login,
            ),
            ProviderConfigRequirement(
                "DATAFORSEO_PASSWORD",
                self.settings.dataforseo_password,
            ),
            analysis_requirement(self.settings),
        ]

    async def search(self, product: str) -> ProviderEvidence:
        self._raise_if_not_configured()
        query_groups = _build_dataforseo_query_groups(product, self.settings)
        sources: list[ProviderRawSource] = []
        api_calls = 0

        try:
            async with self._client_factory() as client:
                for region, query_list in query_groups:
                    location_name = "China" if region in {"china", "china_sourcing"} else "Tunisia"
                    for query in query_list:
                        response = await client.post(
                            "https://api.dataforseo.com/v3/serp/google/organic/live/regular",
                            auth=(
                                self.settings.dataforseo_login,
                                self.settings.dataforseo_password,
                            ),
                            json=[
                                {
                                    "keyword": query,
                                    "language_code": "en",
                                    "location_name": location_name,
                                    "depth": self.settings.search_results_per_query,
                                    "device": "desktop",
                                }
                            ],
                        )
                        api_calls += 1
                        response.raise_for_status()
                        payload = response.json()
                        for task in payload.get("tasks", []):
                            for result in task.get("result", []):
                                for item in result.get("items", []):
                                    if item.get("type") != "organic":
                                        continue
                                    sources.append(
                                        ProviderRawSource(
                                            title=item.get("title", ""),
                                            url=item.get("url", ""),
                                            snippet=item.get("description", "")
                                            or item.get("snippet", ""),
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
        except (AttributeError, KeyError, TypeError, ValueError) as error:
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


def _build_dataforseo_query_groups(product: str, settings):
    raw_query_groups = prioritized_query_groups(product, settings)
    filtered_groups: list[tuple[str, list[str]]] = []
    for region, query_list in raw_query_groups:
        generic_queries = [query for query in query_list if "site:" not in query.lower()]
        filtered_groups.append((region, generic_queries or query_list[:1]))
    return filtered_groups
