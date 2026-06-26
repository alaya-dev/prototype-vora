from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.benchmark.schemas import ProviderEvidence, ProviderInfo, ProductionRisk
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
