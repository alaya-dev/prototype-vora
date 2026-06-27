# VORA AI Prototype - Search Provider Benchmark Lab

FastAPI prototype for benchmarking multiple search and research providers side by side before selecting a production sourcing stack.

## Purpose

The Benchmark Lab answers two questions for the same product:

- Which providers can find the 3 cheapest Tunisian supplier or source options?
- Which providers can find the 3 cheapest Chinese supplier or source options with usable price, MOQ, URL, confidence, and evidence data?

It also tracks latency, provider API usage, Gemini usage, raw query counts, and production risk so the decision is not based on result quality alone.

## Primary Endpoints

- `GET /providers`
- `POST /benchmark/analyze`

## Compatibility Endpoint

`POST /analyze` remains available only for compatibility with the earlier prototype flow. The Benchmark Lab UI does not use it.

## Environment Variables

Benchmark Lab:

```env
GEMINI_INTENT_API_KEY=
GEMINI_INTENT_MODEL=gemini-3.1-flash-lite
GEMINI_ANALYSIS_API_KEY=
GEMINI_ANALYSIS_MODEL=gemini-3.1-flash-lite

SERPER_API_KEY=
BRAVE_SEARCH_API_KEY=
EXA_API_KEY=
FIRECRAWL_API_KEY=
PERPLEXITY_API_KEY=
SEARXNG_BASE_URL=
SCAVIO_API_KEY=
DATAFORSEO_LOGIN=
DATAFORSEO_PASSWORD=

BENCHMARK_PROVIDER_TIMEOUT_SECONDS=45
BENCHMARK_MAX_PROVIDERS_PARALLEL=8
SEARCH_RESULTS_PER_QUERY=10
SEARCH_QUERIES_PER_REGION=4
MAX_RAW_SOURCES_PER_PROVIDER=20
```

Legacy compatibility route:

```env
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.1-flash-lite
ANALYSIS_TIMEOUT_SECONDS=45
```

If the same physical Gemini key is used for both intent and analysis during testing, copy the same value into both `GEMINI_INTENT_API_KEY` and `GEMINI_ANALYSIS_API_KEY`.

## Run Locally

```bash
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```

Open `http://localhost:8000`.

## Configure Providers

- `Serper + Gemini`: set `SERPER_API_KEY` and Gemini intent/analysis keys.
- `Brave Search + Gemini`: set `BRAVE_SEARCH_API_KEY` and Gemini intent/analysis keys.
- `Exa + Gemini`: set `EXA_API_KEY` and Gemini intent/analysis keys.
- `Firecrawl + Gemini`: set `FIRECRAWL_API_KEY` and Gemini intent/analysis keys. This uses Firecrawl's official `POST /v2/search` endpoint and can include markdown content in raw evidence.
- `DataForSEO + Gemini`: set `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD`, and Gemini intent/analysis keys. This uses Google Organic Live Regular SERP with one task per query and conservative generic regional queries first.
- `SearXNG + Gemini`: set `SEARXNG_BASE_URL` and Gemini intent/analysis keys.
- `Perplexity Sonar`: set `PERPLEXITY_API_KEY`; this provider does not use Gemini analysis by default.
- `Scavio + Gemini`: set `SCAVIO_API_KEY` and Gemini intent/analysis keys. This uses the documented `POST https://api.scavio.dev/api/v1/google` Google Search API in light mode. `SCAVIO_BASE_URL` is not required.

`GET /providers` reports configuration state without exposing secrets.

## Run One Provider or All Providers

From the UI:

- Enter a product once.
- Use `Run provider` on an individual card for isolated tests.
- Use `Run all configured providers` to benchmark every configured and enabled provider together.

From the API:

```json
POST /benchmark/analyze
{
  "product": "Vintage T9",
  "providers": ["serper", "brave", "exa", "searxng", "perplexity"]
}
```

If the product is invalid, the API returns HTTP 200 with `intent.is_valid_product=false` and skips all provider calls.

## Interpret Results

Each provider run reports:

- `latency_ms`: end-to-end elapsed time for that provider.
- `raw_sources_count`: number of raw evidence items returned before validation.
- `provider_api_calls`: provider-side request count.
- `gemini_intent_calls`: benchmark-level intent classification calls.
- `gemini_analysis_calls`: evidence extraction calls; this stays `0` for Perplexity by default.
- `raw_queries_count`: generated search queries used by that provider.
- `production_risk`: directional operational risk label, not a final production verdict.
- `cost_notes`: plain-language notes about likely usage shape and pricing uncertainty.

Validated supplier results also show evidence level, confidence, price evidence, MOQ evidence, warnings, and source URLs. Raw evidence is expandable in the UI so provider output can be inspected without overwhelming the main result surface.

The raw-evidence cap is China-aware. When a provider returns more sources than `MAX_RAW_SOURCES_PER_PROVIDER`, the benchmark preserves Chinese evidence first so the cheapest-China path is less likely to be dropped before Gemini extraction and backend validation.

The comparison summary is metric-based. It can highlight the fastest provider, the provider with the most Tunisian or Chinese results, the most source-backed prices, the most complete result set, and the lowest cost risk. It should not be read as an automatic "best production provider" decision.

## Placeholder and Limited Providers

- Firecrawl, DataForSEO, and Scavio are real benchmark providers now, but their pricing, field coverage, and search behavior can still change.

These providers must not block the rest of the benchmark.

## Automated Tests

```bash
python -m unittest discover -s tests -v
```

The test suite uses fake Gemini and provider responses and does not consume live API quota.

## Limitations

- Provider pricing, free tiers, rate limits, supported models, and endpoint behavior may change.
- Search and AI outputs can be incomplete, stale, duplicated, or commercially misleading.
- Benchmark validation reduces risk but does not guarantee supplier correctness.
- Supplier identity, price, MOQ, stock, certifications, and availability still require direct verification.
- Scavio now uses the documented Google Search API contract, but provider pricing, credit rules, and response fields can still change.
- `Perplexity Sonar` returns a web-grounded answer directly, but its output still passes through backend validation and ranking rules.

## Security Notes

- API keys must never be committed.
- Do not expose secrets in logs, responses, frontend text, README examples, or screenshots.
