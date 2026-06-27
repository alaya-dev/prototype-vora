from __future__ import annotations

import httpx

from app.benchmark.providers.base import (
    can_stop_after_source_cap,
    ProviderAdapterError,
    ProviderConfigRequirement,
    SearchProviderAdapter,
    analysis_requirement,
    cap_sources_balanced,
    new_http_client,
    prioritized_query_groups,
)
from app.benchmark.schemas import ProviderEvidence, ProviderRawSource


class ScavioAdapter(SearchProviderAdapter):
    provider_id = "scavio"
    provider_name = "Scavio + Gemini"
    requires_gemini_analysis = True
    production_risk = "medium"
    cost_notes = (
        "Uses Scavio's official Google Search API with one request per raw search "
        "query plus one Gemini analysis call when evidence is found. The benchmark "
        "keeps to light mode and desktop web search to control credit usage."
    )

    def __init__(self, settings):
        super().__init__(settings)
        self._client_factory = new_http_client

    def requirements(self):
        return [
            ProviderConfigRequirement("SCAVIO_API_KEY", self.settings.scavio_api_key),
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
                    country_code = "cn" if region == "china" else "tn"
                    for query in query_list:
                        response = await client.post(
                            "https://api.scavio.dev/api/v1/google",
                            headers={
                                "Authorization": f"Bearer {self.settings.scavio_api_key}",
                                "Content-Type": "application/json",
                            },
                            json={
                                "query": query,
                                "search_type": "classic",
                                "country_code": country_code,
                                "language": "en",
                                "page": 1,
                                "device": "desktop",
                                "nfpr": False,
                            },
                        )
                        api_calls += 1
                        response.raise_for_status()
                        payload = response.json()
                        for item in payload.get("results", []):
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
