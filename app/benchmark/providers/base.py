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
    queries = build_regional_queries(product, settings.search_queries_per_region)
    return [
        ("china", queries.china),
        ("tunisia", queries.tunisia),
    ]


def can_stop_after_source_cap(
    sources: list[ProviderRawSource],
    settings: Settings,
) -> bool:
    if len(sources) < settings.max_raw_sources_per_provider:
        return False
    if settings.max_raw_sources_per_provider <= 1:
        return True

    has_china = any(source.region_hint == "china" for source in sources)
    has_tunisia = any(source.region_hint == "tunisia" for source in sources)
    return has_china and has_tunisia


def cap_sources_balanced(
    sources: list[ProviderRawSource],
    maximum: int,
) -> list[ProviderRawSource]:
    if maximum <= 0 or len(sources) <= maximum:
        return sources[: max(0, maximum)]

    buckets = {"tunisia": [], "china": [], "unknown": []}
    for source in sources:
        buckets.setdefault(source.region_hint, []).append(source)

    selected: list[ProviderRawSource] = []
    while len(selected) < maximum:
        progressed = False
        for region in ("china", "tunisia", "unknown"):
            bucket = buckets.get(region, [])
            if not bucket or len(selected) >= maximum:
                continue
            selected.append(bucket.pop(0))
            progressed = True
        if not progressed:
            break
    return selected
