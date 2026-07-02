from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.benchmark.query_strategy import build_regional_queries
from app.benchmark.schemas import (
    ProviderEvidence,
    ProviderInfo,
    ProductionRisk,
    ProviderRawSource,
)
from app.config import Settings


class ProviderAdapterError(RuntimeError):
    """Raised when a provider fails before returning usable evidence."""


class ProviderNotConfiguredError(ProviderAdapterError):
    """Raised when required provider configuration is missing."""


@dataclass(frozen=True)
class ProviderConfigRequirement:
    name: str
    value: str


class SearchProviderAdapter:
    provider_id: str
    provider_name: str
    requires_gemini_analysis: bool
    production_risk: ProductionRisk
    cost_notes: str
    enabled: bool = True
    limitation_warnings: list[str] = []

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def requirements(self) -> list[ProviderConfigRequirement]:
        return []

    def info(self) -> ProviderInfo:
        missing = [
            requirement.name
            for requirement in self.requirements()
            if not requirement.value
        ]
        return ProviderInfo(
            provider_id=self.provider_id,
            provider_name=self.provider_name,
            configured=not missing and self.enabled,
            enabled=self.enabled,
            requires_gemini_analysis=self.requires_gemini_analysis,
            production_risk=self.production_risk,
            missing_config=missing,
            cost_notes=self.cost_notes,
            warnings=list(self.limitation_warnings),
        )

    async def is_configured(self) -> bool:
        return self.info().configured

    async def search(self, product: str) -> ProviderEvidence:
        raise NotImplementedError

    def _raise_if_not_configured(self) -> None:
        info = self.info()
        if not info.configured:
            raise ProviderNotConfiguredError(
                f"{self.provider_name} is not configured. Missing: {', '.join(info.missing_config)}"
            )


KNOWN_TUNISIAN_RETAIL_DOMAINS = {
    "mytek.tn",
    "jumia.com.tn",
    "tunisianet.com.tn",
    "spacenet.tn",
    "wikishop.tn",
    "shopiwell.tn",
    "keyshop-tn.com",
    "tayara.tn",
    "affariyet.com",
}


def analysis_requirement(settings: Settings) -> ProviderConfigRequirement:
    return ProviderConfigRequirement(
        "GEMINI_ANALYSIS_API_KEY",
        settings.gemini_analysis_api_key,
    )


def new_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30)


def prioritized_query_groups(
    product: str,
    settings: Settings,
) -> list[tuple[str, list[str]]]:
    queries = build_regional_queries(product, settings.effective_search_queries_per_group)
    return [
        ("china_sourcing", queries.china_sourcing),
        ("tunisia_sourcing", queries.tunisia_sourcing),
        ("tunisia_retail", queries.tunisia_retail),
    ]


def can_stop_after_source_cap(
    sources: list[ProviderRawSource],
    settings: Settings,
) -> bool:
    if len(sources) < settings.max_raw_sources_per_provider:
        return False
    if settings.max_raw_sources_per_provider <= 1:
        return True
    if any(source.region_hint in {"tunisia_retail", "tunisia"} for source in sources) and not any(
        _is_known_tunisian_retail_source(source) for source in sources
    ):
        return False

    required_groups = ["china_sourcing", "tunisia_sourcing", "tunisia_retail"][
        : min(settings.max_raw_sources_per_provider, 3)
    ]
    aliases = {
        "china_sourcing": {"china", "china_sourcing"},
        "tunisia_sourcing": {"tunisia_sourcing"},
        "tunisia_retail": {"tunisia", "tunisia_retail"},
    }
    return all(
        any(source.region_hint in aliases[group] for source in sources)
        for group in required_groups
    )


def cap_sources_balanced(
    sources: list[ProviderRawSource],
    maximum: int,
) -> list[ProviderRawSource]:
    if maximum <= 0 or len(sources) <= maximum:
        return sources[: max(0, maximum)]

    selected: list[ProviderRawSource] = []
    seen_urls: set[str] = set()
    priority_retail_sources = [
        source for source in sources
        if _is_known_tunisian_retail_source(source)
    ]
    for source in priority_retail_sources:
        if len(selected) >= maximum:
            break
        key = source.url.lower()
        if key in seen_urls:
            continue
        selected.append(source)
        seen_urls.add(key)

    buckets = {
        "china_sourcing": [],
        "china": [],
        "tunisia_sourcing": [],
        "tunisia_retail": [],
        "tunisia": [],
        "unknown": [],
    }
    for source in sources:
        if source.url.lower() in seen_urls:
            continue
        buckets.setdefault(source.region_hint, []).append(source)

    while len(selected) < maximum:
        progressed = False
        for region in ("china_sourcing", "china", "tunisia_sourcing", "tunisia_retail", "tunisia", "unknown"):
            bucket = buckets.get(region, [])
            if not bucket or len(selected) >= maximum:
                continue
            selected.append(bucket.pop(0))
            progressed = True
        if not progressed:
            break
    return selected


def _is_known_tunisian_retail_source(source: ProviderRawSource) -> bool:
    lowered_url = source.url.lower()
    return source.region_hint in {"tunisia_retail", "tunisia"} and any(
        domain in lowered_url for domain in KNOWN_TUNISIAN_RETAIL_DOMAINS
    )
