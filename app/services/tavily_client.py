from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class TavilySearchResult:
    title: str
    url: str
    content: str


@dataclass(frozen=True)
class TavilySearchResponse:
    results: list[TavilySearchResult]
    warnings: list[str]


class TavilyClient:
    def __init__(
        self,
        api_key: str,
        max_results: int,
        timeout_seconds: int = 15,
    ) -> None:
        self.api_key = api_key
        self.max_results = max_results
        self.timeout_seconds = timeout_seconds

    async def search(self, query: str, max_results: int | None = None) -> TavilySearchResponse:
        payload = {
            "query": query,
            "max_results": max_results or self.max_results,
            "search_depth": "advanced",
            "include_answer": False,
            "include_raw_content": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json=payload,
                    headers=headers,
                )
            response.raise_for_status()
        except httpx.HTTPError as error:
            return TavilySearchResponse(
                results=[],
                warnings=[f'Tavily search failed for query "{query}".'],
            )

        body = response.json()
        results = [
            TavilySearchResult(
                title=(item.get("title") or "Untitled result").strip(),
                url=(item.get("url") or "").strip(),
                content=(item.get("content") or "").strip(),
            )
            for item in body.get("results", [])
            if item.get("url")
        ]
        return TavilySearchResponse(results=results, warnings=[])
