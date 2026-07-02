from __future__ import annotations

import httpx

from app.benchmark.providers.base import (
    ProviderAdapterError,
    ProviderConfigRequirement,
    SearchProviderAdapter,
    analysis_requirement,
    can_stop_after_source_cap,
    cap_sources_balanced,
    new_http_client,
    prioritized_query_groups,
)
from app.benchmark.schemas import ProviderEvidence, ProviderRawSource


class TavilyAdapter(SearchProviderAdapter):
    provider_id = "tavily"
    provider_name = "Tavily + Gemini"
    requires_gemini_analysis = True
    production_risk = "medium"
    cost_notes = (
        "Uses one Tavily Search request per raw query with basic depth by default "
        "plus one Gemini analysis call when evidence is analyzed."
    )

    def __init__(self, settings):
        super().__init__(settings)
        self._client_factory = new_http_client

    def requirements(self):
        return [
            ProviderConfigRequirement("TAVILY_API_KEY", self.settings.tavily_api_key),
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
                    country = "china" if region == "china_sourcing" else "tunisia"
                    for query in query_list:
                        response = await client.post(
                            "https://api.tavily.com/search",
                            headers={
                                "Authorization": f"Bearer {self.settings.tavily_api_key}",
                                "Content-Type": "application/json",
                            },
                            json={
                                "query": query,
                                "search_depth": "basic",
                                "topic": "general",
                                "country": country,
                                "max_results": self.settings.search_results_per_query,
                                "include_answer": False,
                                "include_raw_content": "markdown",
                                "include_images": True,
                                "include_usage": True,
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
                                    content=item.get("raw_content") or None,
                                    region_hint=region,
                                    source_type="search_result",
                                    image_urls=_extract_image_urls(item),
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
            sources=cap_sources_balanced(sources, self.settings.max_raw_sources_per_provider),
            raw_queries_count=api_calls,
            provider_api_calls=api_calls,
        )

    async def search_group(self, product, group: str) -> ProviderEvidence:
        return await _search_one_group(self, product, group)


def _extract_image_urls(item: dict) -> list[str]:
    image_urls: list[str] = []
    for image in item.get("images", []) or []:
        if isinstance(image, dict) and image.get("url"):
            image_urls.append(image["url"])
        elif isinstance(image, str):
            image_urls.append(image)
    image_urls.extend(_collect_nested_image_urls(item))
    return _dedupe_urls(image_urls)


def _collect_nested_image_urls(value) -> list[str]:
    urls: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = str(key).lower()
            if lowered in {"image", "imageurl", "og:image", "twitter:image", "thumbnail", "thumbnailurl"}:
                if isinstance(nested, str) and nested.startswith(("http://", "https://")):
                    urls.append(nested)
                elif isinstance(nested, list):
                    urls.extend(_collect_nested_image_urls(nested))
                elif isinstance(nested, dict):
                    urls.extend(_collect_nested_image_urls(nested))
            elif isinstance(nested, (dict, list)):
                urls.extend(_collect_nested_image_urls(nested))
    elif isinstance(value, list):
        for nested in value:
            urls.extend(_collect_nested_image_urls(nested))
    return urls


def _dedupe_urls(urls: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if not isinstance(url, str) or not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    return deduped


async def _search_one_group(adapter: TavilyAdapter, product, group: str) -> ProviderEvidence:
    from app.benchmark.query_strategy import build_regional_queries

    adapter._raise_if_not_configured()
    query_groups = build_regional_queries(product, adapter.settings.effective_search_queries_per_group)
    query_list = getattr(query_groups, group)
    sources: list[ProviderRawSource] = []
    api_calls = 0
    country = "china" if group == "china_sourcing" else "tunisia"
    try:
        async with adapter._client_factory() as client:
            for query in query_list:
                response = await client.post(
                    "https://api.tavily.com/search",
                    headers={
                        "Authorization": f"Bearer {adapter.settings.tavily_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "query": query,
                        "search_depth": "basic",
                        "topic": "general",
                        "country": country,
                        "max_results": adapter.settings.search_results_per_query,
                        "include_answer": False,
                        "include_raw_content": "markdown",
                        "include_images": True,
                        "include_usage": True,
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
                            content=item.get("raw_content") or None,
                            region_hint=group,
                            source_type="search_result",
                            image_urls=_extract_image_urls(item),
                        )
                    )
                if len(sources) >= adapter.settings.max_raw_sources_per_provider:
                    break
    except httpx.HTTPError as error:
        raise ProviderAdapterError(f"{adapter.provider_name} request failed.") from error
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ProviderAdapterError(
            f"{adapter.provider_name} returned an unexpected response shape."
        ) from error
    return ProviderEvidence(
        provider_id=adapter.provider_id,
        sources=cap_sources_balanced(sources, adapter.settings.max_raw_sources_per_provider),
        raw_queries_count=api_calls,
        provider_api_calls=api_calls,
    )
