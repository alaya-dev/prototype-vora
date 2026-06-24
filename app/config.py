import os
from dataclasses import dataclass

from dotenv import load_dotenv


class SettingsError(RuntimeError):
    """Raised when required environment configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    tavily_api_key: str
    gemini_model: str
    tavily_max_results: int
    tavily_max_queries_per_region: int
    analysis_timeout_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()

        gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        tavily_api_key = os.getenv("TAVILY_API_KEY", "").strip()
        gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite").strip()
        tavily_max_results = _read_int("TAVILY_MAX_RESULTS", default=8, minimum=1)
        tavily_max_queries_per_region = _read_int(
            "TAVILY_MAX_QUERIES_PER_REGION",
            default=4,
            minimum=1,
        )
        analysis_timeout_seconds = _read_int(
            "ANALYSIS_TIMEOUT_SECONDS",
            default=45,
            minimum=5,
        )

        missing_keys = []
        if not gemini_api_key:
            missing_keys.append("GEMINI_API_KEY")
        if not tavily_api_key:
            missing_keys.append("TAVILY_API_KEY")
        if missing_keys:
            joined_keys = ", ".join(missing_keys)
            raise SettingsError(f"Missing required environment variables: {joined_keys}")

        return cls(
            gemini_api_key=gemini_api_key,
            tavily_api_key=tavily_api_key,
            gemini_model=gemini_model,
            tavily_max_results=tavily_max_results,
            tavily_max_queries_per_region=tavily_max_queries_per_region,
            analysis_timeout_seconds=analysis_timeout_seconds,
        )


def _read_int(name: str, default: int, minimum: int) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as error:
        raise SettingsError(f"{name} must be an integer.") from error
    if value < minimum:
        raise SettingsError(f"{name} must be greater than or equal to {minimum}.")
    return value
