# VORA AI Prototype

FastAPI prototype for client-facing product opportunity analysis, sourcing research, provider benchmarking, and internal analytics.

The current primary flow is the VORA/Nexora client prototype:

- One Gemini intent/product-understanding call.
- Firecrawl primary research provider.
- Tavily fallback.
- Exa fallback.
- One Gemini analysis call.
- Client-facing `/prototype/analyze`.
- GO reveal flow for hidden sourcing links and sourcing agents.
- Separate analytics/admin area.

The benchmark lab routes are still available for comparing provider behavior, but the main browser experience is the client analysis flow at `/`.

## What It Does

For a product candidate, the prototype researches:

- China sourcing/manufacturer/wholesale evidence.
- Tunisia wholesale/importer/distributor/manufacturer evidence.
- Tunisia retail market prices with client-facing retail evidence cards.
- Source-backed product image evidence when available.
- Estimated landed cost and campaign-adjusted profitability.
- Conservative GO / NO GO / investigate-more decision scores.

Client responses hide direct China product offer links until the GO reveal endpoint is called. Raw provider search output stays out of the client-facing report.

## Main Routes

- `GET /` - client prototype UI.
- `POST /prototype/analyze` - client-facing product opportunity analysis.
- `GET /prototype/runs/{run_id}/reveal` - GO reveal for hidden sourcing links and configured sourcing agents.
- `GET /analytics` - internal analytics/admin UI.
- `GET /api/analytics/summary` - analytics summary.
- `GET /api/analytics/runs` - run list.
- `GET /api/analytics/runs/{run_id}` - run detail.
- `GET /api/analytics/cost-config` - current cost assumptions.
- `POST /api/analytics/cost-config` - update cost assumptions.
- `GET /api/sourcing-agents` - configured sourcing agents.
- `POST /api/sourcing-agents` - add sourcing agent.
- `PUT /api/sourcing-agents/{agent_id}` - update sourcing agent.
- `DELETE /api/sourcing-agents/{agent_id}` - deactivate sourcing agent.
- `GET /providers` - benchmark provider configuration status without secrets.
- `POST /benchmark/analyze` - provider benchmark analysis.
- `POST /analyze` - legacy compatibility route.
- `GET /health` - health check.

## Provider Stack

The prototype client flow uses this fixed provider order:

1. Firecrawl
2. Tavily
3. Exa

Do not add new required providers or required environment variables for the prototype flow.

The benchmark registry still includes additional providers for comparison work:

- Serper + Gemini
- Brave Search + Gemini
- Exa + Gemini
- Firecrawl + Gemini
- SearXNG + Gemini
- Perplexity Sonar
- Scavio + Gemini
- DataForSEO + Gemini

## Search Query Defaults

For each configured provider in the current default setup, research uses:

- 3 China sourcing / wholesale / manufacturer queries.
- 1 Tunisia wholesale / importer / distributor / manufacturer query.
- 3 Tunisia retail market queries.

That is 7 searches per provider by default. Existing `SEARCH_QUERIES_PER_GROUP` and `SEARCH_QUERIES_PER_REGION` behavior remains backward compatible when explicitly configured.

Tunisia wholesale evidence is intentionally strict. Retail results are not inserted into Tunisia wholesale. If no reliable Tunisian wholesale/importer/distributor/manufacturer offer is found, the response uses a clean not-found message.

## Environment Variables

Minimal client prototype setup:

```env
GEMINI_INTENT_API_KEY=
GEMINI_ANALYSIS_API_KEY=

FIRECRAWL_API_KEY=
TAVILY_API_KEY=
EXA_API_KEY=
```

Optional prototype/admin settings:

```env
GEMINI_INTENT_MODEL=gemini-3.1-flash-lite
GEMINI_ANALYSIS_MODEL=gemini-3.1-flash-lite
ADMIN_DASHBOARD_PASSWORD=

SEARCH_RESULTS_PER_QUERY=10
SEARCH_QUERIES_PER_REGION=4
SEARCH_QUERIES_PER_GROUP=4
MAX_RAW_SOURCES_PER_PROVIDER=20
BENCHMARK_PROVIDER_TIMEOUT_SECONDS=45
BENCHMARK_MAX_PROVIDERS_PARALLEL=8
```

Legacy `/analyze` route:

```env
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.1-flash-lite
ANALYSIS_TIMEOUT_SECONDS=45
```

Optional benchmark-only provider keys:

```env
SERPER_API_KEY=
BRAVE_SEARCH_API_KEY=
PERPLEXITY_API_KEY=
SEARXNG_BASE_URL=
SCAVIO_API_KEY=
SCAVIO_BASE_URL=
DATAFORSEO_LOGIN=
DATAFORSEO_PASSWORD=
```

If the same Gemini key is used for development, copy it into both `GEMINI_INTENT_API_KEY` and `GEMINI_ANALYSIS_API_KEY`.

## Run Locally

```bash
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```

Open:

- Client UI: `http://localhost:8000`
- Analytics UI: `http://localhost:8000/analytics`
- Provider status: `http://localhost:8000/providers`

The app stores prototype run data in `data/vora_prototype.db` by default.

## API Examples

Client prototype analysis:

```json
POST /prototype/analyze
{
  "product": "Vintage T9 hair trimmer",
  "quantity_scenarios": [1000]
}
```

Benchmark analysis:

```json
POST /benchmark/analyze
{
  "product": "Vintage T9 hair trimmer",
  "providers": ["firecrawl", "tavily", "exa"]
}
```

If `providers` is empty in `/benchmark/analyze`, the benchmark pipeline runs all configured and enabled benchmark providers.

## Client Response Notes

`/prototype/analyze` returns a client-safe report with:

- `product_understanding`
- source-backed image metadata, if found
- localized English/French analysis text
- `sourcing_summary`
- `retail_market_summary`
- `profitability_estimate`
- `analysis_quantity_units`
- `decision_scores`
- `recommendation`
- `recommendation_reason`
- `links_hidden=true`

`analysis_quantity_units` defaults to `1000` for the client-facing profitability scenario. `decision_scores.go_percent + decision_scores.no_go_percent` must equal 100. Scores are conservative: weak evidence, missing landed cost, negative margin, or broad/weak product equivalence lowers GO confidence.

Direct China offer URLs and hidden sourcing links are excluded from the client response and are available only through the GO reveal route.

## Frontend Status

The static UI in `static/index.html` includes:

- Branded client analysis page.
- Animated `Analyzing` loader during full analysis.
- Product image/evidence loader while product evidence is being found.
- Source-backed image fallback card.
- Bilingual English/French labels using the local translation map.
- GO / NO GO decision score illustration.
- GO reveal buttons.
- Print/export support.
- Hidden benchmark compatibility block used by tests/manual access.

## Analytics and Admin

The analytics UI is available only at `/analytics`. It is not linked from the client page.

If `ADMIN_DASHBOARD_PASSWORD` is set, analytics and sourcing-agent API routes require the `x-admin-password` header. If it is unset, local development can access analytics without a password.

Analytics tracks provider attempts, fallback path, API usage counts, estimated research cost, image evidence status, retail coverage, hidden sourcing URL counts, and sourcing agent configuration.

## Tests

Run the full suite:

```bash
python -m unittest discover -s tests -v
```

The test suite uses fake Gemini/provider responses and does not consume live API quota.

Current coverage includes:

- Prototype API contract and GO reveal behavior.
- Provider fallback behavior.
- Query distribution and query generation.
- Tunisia wholesale strict not-found behavior.
- Decision-score conservation rules.
- Frontend loader, decision, i18n, and hidden-link checks.
- Benchmark providers and validation.
- Analytics/admin separation.

## Security and Data Rules

- Do not commit API keys.
- Do not expose secrets in logs, responses, frontend text, README examples, or screenshots.
- Do not expose raw provider search results to the client report.
- Do not expose direct China product links on the client side before GO reveal.
- Do not invent prices, images, contacts, MOQ, stock, ratings, availability, or profit guarantees.
- Do not use scraping bypasses, proxies, CAPTCHA solving, or browser automation.

## Limitations

- Search provider results can be incomplete, stale, duplicated, or commercially misleading.
- Supplier identity, price, MOQ, stock, certifications, and availability require direct verification.
- Profitability is an estimate based on source evidence plus admin assumptions, not a guarantee.
- Provider pricing, rate limits, free tiers, and response fields can change.
- Benchmark comparison is directional and should not be treated as an automatic production-provider decision.
