from __future__ import annotations

from app.benchmark.providers.brave import BraveSearchAdapter
from app.benchmark.providers.dataforseo import DataForSEOAdapter
from app.benchmark.providers.exa import ExaAdapter
from app.benchmark.providers.firecrawl import FirecrawlAdapter
from app.benchmark.providers.perplexity import PerplexitySonarAdapter
from app.benchmark.providers.scavio import ScavioAdapter
from app.benchmark.providers.searxng import SearXNGAdapter
from app.benchmark.providers.serper import SerperAdapter
from app.config import Settings


def build_provider_registry(settings: Settings):
    adapters = [
        SerperAdapter(settings),
        BraveSearchAdapter(settings),
        ExaAdapter(settings),
        FirecrawlAdapter(settings),
        SearXNGAdapter(settings),
        PerplexitySonarAdapter(settings),
        ScavioAdapter(settings),
        DataForSEOAdapter(settings),
    ]
    return {adapter.provider_id: adapter for adapter in adapters}
