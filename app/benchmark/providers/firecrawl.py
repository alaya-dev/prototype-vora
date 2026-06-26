from __future__ import annotations

from app.benchmark.providers.base import (
    ProviderConfigRequirement,
    ProviderNotConfiguredError,
    SearchProviderAdapter,
    analysis_requirement,
)
from app.benchmark.schemas import ProviderEvidence


class FirecrawlAdapter(SearchProviderAdapter):
    provider_id = "firecrawl"
    provider_name = "Firecrawl + Gemini"
    requires_gemini_analysis = True
    production_risk = "high"
    cost_notes = (
        "Standalone Firecrawl search is not enabled in this prototype. Firecrawl is "
        "better used as a content extraction layer after URL discovery."
    )
    enabled = False
    limitation_warnings = [
        "Standalone Firecrawl search is limited in this prototype; Firecrawl is better used as a content extraction layer after Serper, Brave, or Exa discovers URLs."
    ]

    def requirements(self):
        return [
            ProviderConfigRequirement(
                "FIRECRAWL_API_KEY",
                self.settings.firecrawl_api_key,
            ),
            analysis_requirement(self.settings),
        ]

    async def search(self, product: str) -> ProviderEvidence:
        raise ProviderNotConfiguredError(
            "Standalone Firecrawl search is disabled in this prototype."
        )
