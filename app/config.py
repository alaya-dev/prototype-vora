import os
from dataclasses import dataclass

from dotenv import load_dotenv


class SettingsError(RuntimeError):
    """Raised when environment configuration is invalid."""


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    analysis_timeout_seconds: int
    gemini_intent_api_key: str = ""
    gemini_intent_model: str = "gemini-3.1-flash-lite"
    gemini_analysis_api_key: str = ""
    gemini_analysis_model: str = "gemini-3.1-flash-lite"
    serper_api_key: str = ""
    brave_search_api_key: str = ""
    exa_api_key: str = ""
    firecrawl_api_key: str = ""
    tavily_api_key: str = ""
    perplexity_api_key: str = ""
    searxng_base_url: str = ""
    scavio_api_key: str = ""
    scavio_base_url: str = ""
    dataforseo_login: str = ""
    dataforseo_password: str = ""
    benchmark_provider_timeout_seconds: int = 45
    benchmark_max_providers_parallel: int = 8
    search_results_per_query: int = 10
    search_queries_per_region: int = 4
    search_queries_per_group: int = 4
    max_raw_sources_per_provider: int = 20
    admin_dashboard_password: str = ""

    @property
    def effective_search_queries_per_group(self) -> int:
        if self.search_queries_per_group == 4 and self.search_queries_per_region != 4:
            return self.search_queries_per_region
        return self.search_queries_per_group

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()

        return cls(
            gemini_intent_api_key=_read_str("GEMINI_INTENT_API_KEY"),
            gemini_intent_model=_read_str("GEMINI_INTENT_MODEL", "gemini-3.1-flash-lite"),
            gemini_analysis_api_key=_read_str("GEMINI_ANALYSIS_API_KEY"),
            gemini_analysis_model=_read_str("GEMINI_ANALYSIS_MODEL", "gemini-3.1-flash-lite"),
            gemini_api_key=_read_str("GEMINI_API_KEY"),
            gemini_model=_read_str("GEMINI_MODEL", "gemini-3.1-flash-lite"),
            analysis_timeout_seconds=_read_int(
                "ANALYSIS_TIMEOUT_SECONDS",
                default=45,
                minimum=5,
            ),
            serper_api_key=_read_str("SERPER_API_KEY"),
            brave_search_api_key=_read_str("BRAVE_SEARCH_API_KEY"),
            exa_api_key=_read_str("EXA_API_KEY"),
            firecrawl_api_key=_read_str("FIRECRAWL_API_KEY"),
            tavily_api_key=_read_str("TAVILY_API_KEY"),
            perplexity_api_key=_read_str("PERPLEXITY_API_KEY"),
            searxng_base_url=_read_str("SEARXNG_BASE_URL"),
            scavio_api_key=_read_str("SCAVIO_API_KEY"),
            scavio_base_url=_read_str("SCAVIO_BASE_URL"),
            dataforseo_login=_read_str("DATAFORSEO_LOGIN"),
            dataforseo_password=_read_str("DATAFORSEO_PASSWORD"),
            benchmark_provider_timeout_seconds=_read_int(
                "BENCHMARK_PROVIDER_TIMEOUT_SECONDS",
                default=45,
                minimum=1,
            ),
            benchmark_max_providers_parallel=_read_int(
                "BENCHMARK_MAX_PROVIDERS_PARALLEL",
                default=8,
                minimum=1,
            ),
            search_results_per_query=_read_int(
                "SEARCH_RESULTS_PER_QUERY",
                default=10,
                minimum=1,
            ),
            search_queries_per_region=_read_int(
                "SEARCH_QUERIES_PER_REGION",
                default=4,
                minimum=1,
            ),
            search_queries_per_group=_read_int(
                "SEARCH_QUERIES_PER_GROUP",
                default=_read_int(
                    "SEARCH_QUERIES_PER_REGION",
                    default=4,
                    minimum=1,
                ),
                minimum=1,
            ),
            max_raw_sources_per_provider=_read_int(
                "MAX_RAW_SOURCES_PER_PROVIDER",
                default=20,
                minimum=1,
            ),
            admin_dashboard_password=_read_str("ADMIN_DASHBOARD_PASSWORD"),
        )


def _read_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _read_int(name: str, default: int, minimum: int) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as error:
        raise SettingsError(f"{name} must be an integer.") from error
    if value < minimum:
        raise SettingsError(f"{name} must be greater than or equal to {minimum}.")
    return value
