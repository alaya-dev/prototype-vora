from __future__ import annotations

from app.benchmark.providers.base import (
    ProviderConfigRequirement,
    ProviderNotConfiguredError,
    SearchProviderAdapter,
    analysis_requirement,
)
from app.benchmark.schemas import ProviderEvidence


class ScavioAdapter(SearchProviderAdapter):
    provider_id = "scavio"
    provider_name = "Scavio + Gemini"
    requires_gemini_analysis = True
    production_risk = "high"
    cost_notes = (
        "Scavio is disabled in this prototype until an official API contract is supplied."
    )
    enabled = False
    limitation_warnings = [
        "Scavio search is disabled until an official API contract is supplied."
    ]

    def requirements(self):
        return [
            ProviderConfigRequirement("SCAVIO_API_KEY", self.settings.scavio_api_key),
            ProviderConfigRequirement("SCAVIO_BASE_URL", self.settings.scavio_base_url),
            analysis_requirement(self.settings),
        ]

    async def search(self, product: str) -> ProviderEvidence:
        raise ProviderNotConfiguredError(
            "Scavio is disabled in this prototype."
        )
