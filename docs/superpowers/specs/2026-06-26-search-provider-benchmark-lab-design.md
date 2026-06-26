# Search Provider Benchmark Lab Design

## Objective

Transform the VORA AI prototype from a single research-agent MVP into a Search Provider Benchmark Lab. The lab compares multiple search and research providers side by side for the same product before choosing a production sourcing stack.

The main business question is whether each provider can help VORA find:

- the 3 cheapest Tunisian supplier or source options;
- the 3 cheapest Chinese supplier or source options;
- source URLs;
- Tunisian prices in TND;
- Chinese prices in USD;
- China MOQ when available;
- confidence, evidence quality, latency, usage, cost, and production risk.

The benchmark is not a final production-provider decision engine. It reports metric-based comparisons so humans can judge result quality, cost, and reliability.

## Existing Endpoint Compatibility

The repository currently exposes `/analyze`. Keep that endpoint for compatibility if it already exists in the codebase, but the Benchmark Lab UI must use `/benchmark/analyze` as the primary endpoint.

The old route should not drive the new UI. It may continue to use the existing implementation until a separate compatibility decision is made. The new benchmark design does not depend on the old route's research method.

## Architecture

Add a new benchmark layer beside the existing MVP code:

```text
BenchmarkPipeline
|-- GeminiIntentClient / IntentClassifierAgent
|-- ProviderRegistry
|   |-- SerperAdapter
|   |-- BraveSearchAdapter
|   |-- ExaAdapter
|   |-- FirecrawlAdapter
|   |-- SearXNGAdapter
|   |-- PerplexitySonarAdapter
|   |-- ScavioAdapter
|   `-- DataForSEOAdapter
|-- GeminiAnalysisClient
|-- ProviderResultValidator
`-- ComparisonSummaryBuilder
```

Recommended module layout:

- `app/benchmark/schemas.py`: benchmark request, response, evidence, provider status, supplier extraction, usage, and comparison models.
- `app/benchmark/providers/base.py`: adapter interface and common evidence helpers.
- `app/benchmark/providers/*.py`: provider-specific adapters.
- `app/benchmark/query_strategy.py`: internal Tunisia and China query generation.
- `app/benchmark/pipeline.py`: intent gating, concurrent provider execution, timeout handling, and partial response assembly.
- `app/benchmark/validation.py`: URL checks, dedupe, confidence downgrades, sorting, caps, and warning rules.
- `app/benchmark/comparison.py`: metric-based comparison summary.
- `app/services/gemini_client.py` or a small adjacent wrapper module: logically separate `GeminiIntentClient` and `GeminiAnalysisClient`.

## Gemini Client Boundaries

Use Gemini, but do not use Gemini as the search engine for the benchmark providers.

`GeminiIntentClient` runs exactly once per `/benchmark/analyze` request before any provider call. It classifies and normalizes the product. If the product is invalid, the API returns HTTP 200 with `is_valid_product=false`, no provider is called, and provider run usage counters remain absent or zero.

`GeminiAnalysisClient` is used only for providers that return evidence requiring structured extraction:

- Serper
- Brave Search
- Exa
- Firecrawl when used as an evidence or search source
- SearXNG
- Scavio if later implemented
- DataForSEO if later implemented

Perplexity Sonar must not use `GeminiAnalysisClient` by default because it returns a web-grounded AI answer. Perplexity output still goes through backend validation, URL checks, evidence downgrade rules, sorting, and max result caps.

The logical clients use separate environment variables:

```env
GEMINI_INTENT_API_KEY=
GEMINI_INTENT_MODEL=
GEMINI_ANALYSIS_API_KEY=
GEMINI_ANALYSIS_MODEL=
```

The same physical key may be copied into both variables during testing, but the code keeps the two client roles separate.

## Provider Adapter Interface

Each provider implements a common async adapter interface:

```python
class SearchProviderAdapter:
    provider_id: str
    provider_name: str
    requires_gemini_analysis: bool
    production_risk: Literal["low", "medium", "high"]

    async def is_configured(self) -> bool:
        ...

    async def search(self, product: str) -> ProviderEvidence:
        ...
```

Provider evidence is normalized before analysis:

```json
{
  "provider_id": "",
  "sources": [
    {
      "title": "",
      "url": "",
      "snippet": "",
      "content": null,
      "region_hint": "tunisia|china|unknown",
      "source_type": "search_result|product_page|supplier_profile|marketplace|unknown"
    }
  ],
  "raw_queries_count": 0,
  "provider_api_calls": 0,
  "warnings": [],
  "errors": []
}
```

Adapters must never expose API keys in responses, logs, exceptions, frontend text, or documentation.

## Provider List

### Serper + Gemini Analysis

Use the official Serper HTTP API with `SERPER_API_KEY`. The adapter generates internal Tunisia and China query sets, calls Serper, normalizes organic results into evidence, and sends the evidence to `GeminiAnalysisClient`.

Production risk defaults to `medium` because result quality depends on search result snippets and pricing/free-tier behavior.

### Brave Search + Gemini Analysis

Use Brave Search API with `BRAVE_SEARCH_API_KEY`. The adapter normalizes web results into evidence, then uses `GeminiAnalysisClient`.

Production risk defaults to `medium`.

### Exa + Gemini Analysis

Use Exa with `EXA_API_KEY`. The adapter should prefer search/content results when available, include useful page text in `content`, and use `GeminiAnalysisClient`.

Production risk defaults to `medium` until benchmark results show stable sourcing coverage.

### Firecrawl + Gemini Analysis

Handle Firecrawl honestly.

If the configured Firecrawl API supports standalone search through a clear official endpoint, implement it as an experimental provider using `FIRECRAWL_API_KEY`, normalize the returned search or extraction evidence, and use `GeminiAnalysisClient`.

If only scrape/extract after URL discovery is practical in the current implementation, the standalone Firecrawl provider returns `not_configured` or `disabled` with a clear limitation warning. The warning should explain that Firecrawl is better suited as a content extraction layer after Serper, Brave, or Exa discovers URLs. The adapter must not fake standalone search results.

Production risk defaults to `high` for standalone provider mode until live search behavior is verified.

### SearXNG + Gemini Analysis

Use a configurable `SEARXNG_BASE_URL` and query `/search` with JSON output when available. Normalize results and use `GeminiAnalysisClient`.

Production risk defaults to `medium` or `high` depending on whether the configured instance is self-hosted and stable.

### Perplexity Sonar

Use `PERPLEXITY_API_KEY` to ask Sonar directly for strict JSON matching the benchmark extraction schema. It should be prompted to return web-grounded supplier evidence with source URLs and no invented prices or MOQ.

This provider sets `requires_gemini_analysis=false`, `gemini_analysis_calls=0`, and still passes through the same backend validator.

Production risk defaults to `medium` because the result is an AI-composed answer and must be validated.

### Scavio + Gemini Analysis

If a simple official HTTP API key/base URL contract is available, implement it with `SCAVIO_API_KEY` and `SCAVIO_BASE_URL`.

If the API contract is unclear, create a clean adapter placeholder. It returns `not_configured` until credentials and endpoint details are supplied. It must not hardcode unofficial endpoints.

Production risk defaults to `high` while placeholder or unverified.

### DataForSEO + Gemini Analysis

DataForSEO is optional. If implementation is lightweight, add a basic search adapter using `DATAFORSEO_LOGIN` and `DATAFORSEO_PASSWORD`. If it adds too much complexity, include the adapter interface and return `disabled` or `not_configured`.

The provider must not block the rest of the benchmark.

Production risk defaults to `low` only after a real implementation exists and credentials are configured; otherwise `medium` or `high` with notes.

## Query Strategy

Query-based providers generate internal query sets. Use configuration to cap breadth:

```env
SEARCH_RESULTS_PER_QUERY=10
SEARCH_QUERIES_PER_REGION=4
MAX_RAW_SOURCES_PER_PROVIDER=20
```

Tunisia examples:

- `{product} prix Tunisie`
- `{product} achat Tunisie`
- `{product} boutique Tunisie`
- `{product} site:mytek.tn`
- `{product} site:jumia.com.tn`
- `{product} site:tayara.tn`
- `{product} site:spacenet.tn`
- `{product} site:shopiwell.tn`
- `{product} site:barka.tn`

China examples:

- `{product} China supplier price MOQ`
- `{product} manufacturer China wholesale`
- `{product} Alibaba supplier MOQ price`
- `{product} Made-in-China supplier`
- `{product} Global Sources supplier`
- `{product} wholesale China factory`
- `{product} OEM ODM supplier`

Select the first configured number of queries per region. Track `raw_queries_count`.

Do not scrape protected pages directly. Do not bypass anti-bot systems. Do not use proxies, CAPTCHA solving, browser automation, or evasion techniques. Use only official APIs and publicly available search/provider outputs.

## Extraction Schema

For providers that require Gemini analysis, send normalized provider evidence to `GeminiAnalysisClient` and request strict JSON:

```json
{
  "market_summary": "",
  "tunisia_cheapest_suppliers": [
    {
      "rank": 1,
      "name": "",
      "type": "marketplace|local_provider|seller|source|unknown",
      "product_title": null,
      "price_range_tnd": null,
      "price_min_tnd_numeric": null,
      "price_max_tnd_numeric": null,
      "source_url": "",
      "evidence_level": "direct|indirect|weak",
      "price_evidence": "direct|snippet|not_found",
      "confidence": "high|medium|low",
      "notes": ""
    }
  ],
  "china_cheapest_suppliers": [
    {
      "rank": 1,
      "name": "",
      "type": "manufacturer|trading_company|marketplace_source|supplier_profile|unknown",
      "product_title": null,
      "price_range_usd": null,
      "price_min_usd_numeric": null,
      "price_max_usd_numeric": null,
      "moq": null,
      "moq_numeric": null,
      "source_url": "",
      "evidence_level": "direct|indirect|weak",
      "price_evidence": "direct|snippet|not_found",
      "moq_evidence": "direct|snippet|not_found",
      "confidence": "high|medium|low",
      "notes": ""
    }
  ],
  "research_sources": [],
  "warnings": [],
  "data_quality_notes": "",
  "missing_data": {
    "tunisia": "",
    "china": ""
  }
}
```

The backend treats extraction output as untrusted and validates it before returning it.

## Validation and Ranking

Validation is mandatory for every provider, including Perplexity.

Rules:

1. Validate URLs syntactically and require `http` or `https`.
2. Remove duplicate URLs from research sources and supplier lists.
3. Downgrade homepage-only URLs to `evidence_level="weak"` and `confidence="low"`.
4. Search result URLs cannot have confidence higher than `medium`.
5. Missing price means `price_evidence="not_found"` and numeric price fields are null.
6. Missing MOQ means `moq_evidence="not_found"` and `moq_numeric` is null.
7. High confidence requires direct evidence.
8. Sort Tunisia results by `price_min_tnd_numeric` ascending.
9. Sort China results by `price_min_usd_numeric` ascending.
10. Results without price do not appear in the cheapest top 3 unless fewer than 3 price-backed results exist.
11. Cap Tunisia results at 3 and China results at 3.
12. Return fewer than 3 results with a warning when fewer valid results exist.
13. Do not invent suppliers, prices, MOQ, stock, ratings, availability, or fallback sources.
14. Do not add curated fallback sourcing agents.

The validator also ensures research sources are deduplicated and raw source counts are computed from provider evidence rather than model claims.

## Run Status and Usage Model

Provider run status is normalized to:

- `success`
- `partial`
- `failed`
- `not_configured`
- `disabled`
- `timeout`

Each provider run includes:

```json
{
  "provider_id": "",
  "provider_name": "",
  "status": "success|partial|failed|not_configured|disabled|timeout",
  "uses_gemini_intent": true,
  "uses_gemini_analysis": true,
  "latency_ms": 0,
  "raw_sources_count": 0,
  "provider_api_calls": 0,
  "gemini_intent_calls": 1,
  "gemini_analysis_calls": 0,
  "raw_queries_count": 0,
  "cost_notes": "",
  "production_risk": "low|medium|high",
  "market_summary": "",
  "tunisia_cheapest_suppliers": [],
  "china_cheapest_suppliers": [],
  "research_sources": [],
  "raw_sources": [],
  "warnings": [],
  "errors": []
}
```

For invalid products, provider runs are not executed. For configured providers, `gemini_intent_calls=1` reflects the shared benchmark-level intent call. `gemini_analysis_calls` is `1` only when that provider uses Gemini extraction and reaches that phase. It is always `0` for Perplexity by default.

Cost notes are plain text and should state known uncertainty, such as provider pricing and free tiers changing over time.

## API Endpoints

### `GET /providers`

Returns provider configuration status without exposing secrets.

Example fields:

```json
{
  "providers": [
    {
      "provider_id": "brave",
      "provider_name": "Brave Search + Gemini",
      "configured": true,
      "enabled": true,
      "requires_gemini_analysis": true,
      "production_risk": "medium",
      "missing_config": [],
      "cost_notes": ""
    }
  ]
}
```

### `POST /benchmark/analyze`

Input:

```json
{
  "product": "Vintage T9",
  "providers": ["serper", "brave", "exa", "firecrawl", "searxng", "perplexity", "scavio", "dataforseo"]
}
```

Output:

```json
{
  "product": "Vintage T9",
  "normalized_product": "",
  "intent": {
    "is_valid_product": true,
    "reason": ""
  },
  "runs": [],
  "comparison_summary": {
    "fastest_provider": null,
    "most_tunisian_results": null,
    "most_chinese_results": null,
    "most_source_backed_prices": null,
    "most_complete_provider": null,
    "lowest_cost_risk": null,
    "notes": ""
  }
}
```

If the product is invalid, return HTTP 200 with `intent.is_valid_product=false`, no provider runs, and a comparison note explaining that provider calls were skipped.

Provider failures, timeouts, disabled providers, and missing credentials must not break the whole benchmark.

## Concurrency and Timeout

Use:

```env
BENCHMARK_PROVIDER_TIMEOUT_SECONDS=45
BENCHMARK_MAX_PROVIDERS_PARALLEL=8
```

The benchmark pipeline runs providers concurrently with a semaphore. Each provider has an independent timeout. A timeout produces a provider run with `status="timeout"` and does not cancel other providers.

Unexpected provider errors produce `status="failed"` for that provider and a sanitized error message. The API still returns HTTP 200 when at least the benchmark request itself is valid.

## Comparison Summary

The comparison summary is metric-based. It may report:

- fastest provider;
- most Tunisian results;
- most Chinese results;
- most source-backed prices;
- most complete provider;
- lowest cost risk;
- notes.

It must not claim a provider is the best production provider unless the measured data clearly supports that statement. In normal benchmark runs, notes should frame the output as directional and dependent on provider coverage, pricing, latency, and repeated tests.

## Frontend

Replace the static page with a Benchmark Lab UI that uses `/providers` and `/benchmark/analyze`.

The UI includes:

- one common product input at the top;
- provider cards/forms for each provider;
- status labels: configured, missing key, disabled, running, success, partial, failed, not_configured, timeout;
- run button per provider;
- run all configured providers button;
- latency in milliseconds;
- raw source count;
- Tunisian result count;
- Chinese result count;
- provider API calls;
- Gemini intent calls;
- Gemini analysis calls;
- raw query count;
- cost notes;
- production risk;
- errors and warnings;
- result panels per provider.

Each result panel shows:

- market summary;
- up to 3 cheapest Tunisian suppliers;
- up to 3 cheapest Chinese suppliers;
- source URLs;
- evidence level;
- confidence;
- price evidence;
- MOQ evidence;
- warnings;
- raw evidence in an expandable/collapsible section.

The raw evidence section must be collapsed by default or visually quiet enough that the UI remains readable.

## Configuration

`.env.example` and README document:

```env
GEMINI_INTENT_API_KEY=
GEMINI_INTENT_MODEL=
GEMINI_ANALYSIS_API_KEY=
GEMINI_ANALYSIS_MODEL=
SERPER_API_KEY=
BRAVE_SEARCH_API_KEY=
EXA_API_KEY=
FIRECRAWL_API_KEY=
PERPLEXITY_API_KEY=
SEARXNG_BASE_URL=
SCAVIO_API_KEY=
SCAVIO_BASE_URL=
DATAFORSEO_LOGIN=
DATAFORSEO_PASSWORD=
BENCHMARK_PROVIDER_TIMEOUT_SECONDS=45
BENCHMARK_MAX_PROVIDERS_PARALLEL=8
SEARCH_RESULTS_PER_QUERY=10
SEARCH_QUERIES_PER_REGION=4
MAX_RAW_SOURCES_PER_PROVIDER=20
```

Secrets are never committed. Responses and errors must name missing variables but must not include secret values.

## Testing

Add or update unittest coverage for:

- provider configuration status;
- intent called once per benchmark request;
- invalid product suppresses all providers;
- Perplexity does not use `GeminiAnalysisClient`;
- provider timeout returns `timeout` and does not break the full benchmark;
- missing API key returns `not_configured`;
- provider failure returns a failed run and does not break other runs;
- backend validation downgrades weak evidence;
- homepage-only URLs are downgraded;
- search result URLs cannot exceed medium confidence;
- high confidence requires direct evidence;
- cheapest sorting returns the cheapest 3 Tunisia results;
- cheapest sorting returns the cheapest 3 China results;
- URL deduplication works;
- max 3 Tunisia and max 3 China results are enforced;
- usage and cost fields are returned;
- Firecrawl limited/not_configured behavior works when standalone search is unavailable;
- frontend contains provider cards, run-all behavior, usage fields, and expandable raw evidence.

Tests use fake adapters and fake Gemini clients. They must not require live provider credentials or consume API quota.

## Documentation

Update README with:

- purpose of the Benchmark Lab;
- environment variables;
- local run instructions;
- provider configuration instructions;
- how to run one provider and all configured providers;
- how to interpret result quality, usage, and production risk;
- placeholder providers and limitations;
- warning that API keys must never be committed;
- warning that provider pricing, rate limits, and free tiers may change.

## Known Limitations

Provider APIs may return stale, incomplete, duplicated, or commercially misleading results. Search result snippets are not equivalent to direct product-page evidence. Perplexity can provide a web-grounded answer, but its structured output still requires backend validation. Firecrawl may be better as a content extraction layer than as a standalone discovery provider depending on the available API contract. Scavio and DataForSEO may remain placeholders until official endpoint details and credentials are available.

The benchmark is one input into production provider selection. Repeated runs across product categories, time windows, and provider configurations are needed before making a production decision.
