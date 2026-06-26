from __future__ import annotations

from app.benchmark.providers.base import (
    ProviderConfigRequirement,
    ProviderNotConfiguredError,
    SearchProviderAdapter,
    analysis_requirement,
)
from app.benchmark.schemas import ProviderEvidence


class DataForSEOAdapter(SearchProviderAdapter):
    provider_id = "dataforseo"
    provider_name = "DataForSEO + Gemini"
    requires_gemini_analysis = True
    production_risk = "medium"
    cost_notes = (
        "DataForSEO is disabled in this prototype until the production search task "
        "contract is selected."
    )
    enabled = False
    limitation_warnings = [
        "DataForSEO is disabled in this prototype until the production search task contract is selected."
    ]

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
        raise ProviderNotConfiguredError(
            "DataForSEO is disabled in this prototype."
        )
