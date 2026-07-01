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


class FirecrawlAdapter(SearchProviderAdapter):
    provider_id = "firecrawl"
    provider_name = "Firecrawl + Gemini"
    requires_gemini_analysis = True
    production_risk = "high"
    cost_notes = (
        "Uses one Firecrawl Search request per raw search query plus one Gemini "
        "analysis call when evidence is found. Search can also return markdown "
        "content, which increases payload size and may affect cost."
    )

    def __init__(self, settings):
        super().__init__(settings)
        self._client_factory = new_http_client

    def requirements(self):
        return [
            ProviderConfigRequirement(
                "FIRECRAWL_API_KEY",
                self.settings.firecrawl_api_key,
            ),
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
                    location = "China" if region in {"china", "china_sourcing"} else "Tunisia"
                    for query in query_list:
                        response = await client.post(
                            "https://api.firecrawl.dev/v2/search",
                            headers={
                                "Authorization": f"Bearer {self.settings.firecrawl_api_key}",
                                "Content-Type": "application/json",
                            },
                            json={
                                "query": query,
                                "limit": self.settings.search_results_per_query,
                                "sources": ["web"],
                                "location": location,
                            },
                        )
                        api_calls += 1
                        response.raise_for_status()
                        payload = response.json()
                        if not payload.get("success", True):
                            raise ProviderAdapterError(
                                f"{self.provider_name} request failed."
                            )
                        for item in _extract_firecrawl_items(payload):
                            sources.append(
                                ProviderRawSource(
                                    title=item.get("title", ""),
                                    url=item.get("url", ""),
                                    snippet=item.get("description", "")
                                    or item.get("snippet", ""),
                                    content=item.get("markdown")
                                    or item.get("summary")
                                    or None,
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
        except ProviderAdapterError:
            raise
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

    async def search_group(self, product: str, group: str) -> ProviderEvidence:
        from app.benchmark.query_strategy import build_regional_queries

        self._raise_if_not_configured()
        query_groups = build_regional_queries(product, self.settings.effective_search_queries_per_group)
        query_list = getattr(query_groups, group)
        location = "China" if group == "china_sourcing" else "Tunisia"
        sources: list[ProviderRawSource] = []
        api_calls = 0
        try:
            async with self._client_factory() as client:
                for query in query_list:
                    response = await client.post(
                        "https://api.firecrawl.dev/v2/search",
                        headers={
                            "Authorization": f"Bearer {self.settings.firecrawl_api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "query": query,
                            "limit": self.settings.search_results_per_query,
                            "sources": ["web"],
                            "location": location,
                        },
                    )
                    api_calls += 1
                    response.raise_for_status()
                    payload = response.json()
                    if not payload.get("success", True):
                        raise ProviderAdapterError(
                            f"{self.provider_name} request failed."
                        )
                    for item in _extract_firecrawl_items(payload):
                        sources.append(
                            ProviderRawSource(
                                title=item.get("title", ""),
                                url=item.get("url", ""),
                                snippet=item.get("description", "")
                                or item.get("snippet", ""),
                                content=item.get("markdown")
                                or item.get("summary")
                                or None,
                                image_urls=_extract_firecrawl_images(item),
                                region_hint=group,
                                source_type="search_result",
                            )
                        )
                    if len(sources) >= self.settings.max_raw_sources_per_provider:
                        break
        except httpx.HTTPError as error:
            raise ProviderAdapterError(f"{self.provider_name} request failed.") from error
        except ProviderAdapterError:
            raise
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


def _extract_firecrawl_items(payload: dict) -> list[dict]:
    data = payload.get("data", {})
    if isinstance(data, dict):
        return data.get("web", [])
    if isinstance(data, list):
        return data
    raise TypeError("Unexpected Firecrawl data shape.")


def _extract_firecrawl_images(item: dict) -> list[str]:
    image = item.get("image") or item.get("imageUrl")
    images = item.get("images") or []
    urls = []
    if isinstance(image, str):
        urls.append(image)
    for value in images:
        if isinstance(value, str):
            urls.append(value)
        elif isinstance(value, dict) and value.get("url"):
            urls.append(value["url"])
    return urls
