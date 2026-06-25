# Gemini Search-Grounded Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Tavily research with Gemini 3.1 Flash-Lite Google Search-grounded Tunisia and China research while preserving the existing API contract and invalid-input behavior.

**Architecture:** Keep the existing structured `GeminiClient` for intent classification and add a focused `GeminiSearchClient` around the Google Gen AI Interactions API. Two regional agents call that client concurrently, validate grounded JSON, reconcile supplier URLs against citation annotations, and let the pipeline return partial results when only one region fails.

**Tech Stack:** Python, FastAPI, Pydantic v2, google-genai 2.10+, unittest, static HTML/CSS/JavaScript

---

## File Structure

- Modify `app/config.py`: remove Tavily settings and default Gemini to 3.1 Flash-Lite.
- Create `app/services/gemini_search_client.py`: execute grounded Interactions API calls, retry malformed JSON once, and extract citations.
- Modify `app/services/provenance.py`: reconcile model supplier URLs with grounding citation URLs and downgrade unsourced options.
- Replace `app/agents/market_research.py`: implement `GeminiTunisiaResearchAgent`.
- Replace `app/agents/china_supplier_research.py`: implement `GeminiChinaSupplierResearchAgent`.
- Modify `app/pipeline.py`: isolate regional failures while retaining timeout and warning behavior.
- Modify `server.py`: construct only Gemini clients and new regional agents.
- Delete `app/services/tavily_client.py`: remove obsolete integration.
- Modify `requirements.txt`, `.env.example`, `README.md`, and `static/index.html`: remove Tavily configuration and copy.
- Replace and extend tests under `tests/`: drive each behavior before implementation.

### Task 1: Configuration and Application Wiring

**Files:**
- Modify: `tests/test_config.py`
- Modify: `tests/test_api.py`
- Modify: `app/config.py`
- Modify: `server.py`

- [ ] **Step 1: Write failing configuration tests**

Update tests to construct `Settings` with only:

```python
Settings(
    gemini_api_key="test-gemini",
    gemini_model="gemini-3.1-flash-lite",
    analysis_timeout_seconds=45,
)
```

Assert that `Settings.from_env()` requires only `GEMINI_API_KEY`, defaults `GEMINI_MODEL` to `gemini-3.1-flash-lite`, and ignores absent Tavily variables.

- [ ] **Step 2: Run configuration and API tests to verify failure**

Run:

```powershell
python -m unittest tests.test_config tests.test_api -v
```

Expected: failures caused by obsolete Tavily fields and requirements.

- [ ] **Step 3: Implement the minimal settings change**

Reduce `Settings` to:

```python
@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    analysis_timeout_seconds: int
```

Default the model to `gemini-3.1-flash-lite`. Remove all Tavily environment reads and validation.

- [ ] **Step 4: Update server imports and construction boundary**

Change server wiring to import the new class names that later tasks will implement:

```python
GeminiTunisiaResearchAgent
GeminiChinaSupplierResearchAgent
GeminiSearchClient
```

Construct one `GeminiClient` for intent classification and one `GeminiSearchClient` for both regional agents.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m unittest tests.test_config tests.test_api -v
```

Expected: PASS after the new agent/client modules exist in Task 3; during this task, use test-only import isolation or defer the server wiring assertion until Task 3 rather than adding production stubs.

### Task 2: Grounded Interactions Client

**Files:**
- Create: `tests/test_gemini_search_client.py`
- Create: `app/services/gemini_search_client.py`

- [ ] **Step 1: Write a failing test for grounded request configuration**

Use a fake async interactions endpoint that records keyword arguments. Assert the client sends:

```python
{
    "model": "gemini-3.1-flash-lite",
    "input": prompt,
    "tools": [{"type": "google_search"}],
    "store": False,
}
```

and returns a Pydantic-validated payload.

- [ ] **Step 2: Run the test and verify failure**

Run:

```powershell
python -m unittest tests.test_gemini_search_client.GeminiSearchClientTests.test_grounded_request_uses_google_search_tool -v
```

Expected: import or missing-class failure.

- [ ] **Step 3: Implement the client request and response value**

Create:

```python
@dataclass(frozen=True)
class GroundedResponse(Generic[T]):
    payload: T
    citations: list[GroundingCitation]

@dataclass(frozen=True)
class GroundingCitation:
    title: str
    url: str
```

`GeminiSearchClient.generate_grounded_json()` calls `self._client.aio.interactions.create(...)`.

- [ ] **Step 4: Write failing citation extraction tests**

Build fake interaction steps using simple objects with:

- one `google_search_call`;
- one `model_output`;
- one text block containing JSON;
- duplicate `url_citation` annotations.

Assert citations are deduplicated in first-seen order.

- [ ] **Step 5: Implement step inspection**

Use attribute access helpers that support SDK Pydantic objects and test fakes. Require a search-call step and concatenate text from model output blocks. Extract only annotations whose type is `url_citation` and whose URL is non-empty.

- [ ] **Step 6: Write failing retry and rejection tests**

Cover:

- first malformed output, second valid output;
- two malformed outputs;
- valid JSON without a `google_search_call`;
- no model output.

Assert exactly two calls for malformed JSON and `GeminiSearchClientError` for terminal failures.

- [ ] **Step 7: Implement strict retry behavior**

Catch only parsing and Pydantic validation failures for the JSON retry. On the second attempt append:

```text
Return only one valid JSON object matching the requested schema. Do not include markdown fences or commentary.
```

Map remote errors through the existing Gemini error-message helper without exposing response bodies or keys.

- [ ] **Step 8: Run the client tests**

Run:

```powershell
python -m unittest tests.test_gemini_search_client -v
```

Expected: PASS.

### Task 3: Regional Agents and Citation Provenance

**Files:**
- Replace: `tests/test_research_agents.py`
- Modify: `tests/test_url_provenance.py`
- Modify: `app/services/provenance.py`
- Replace: `app/agents/market_research.py`
- Replace: `app/agents/china_supplier_research.py`
- Modify: `server.py`
- Delete: `app/services/tavily_client.py`

- [ ] **Step 1: Write failing provenance tests**

Specify these cases:

```python
# cited URL -> preserved confidence and URL
# uncited URL -> URL cleared and confidence low
# absent URL -> confidence low
```

The reconciliation function must not discard URL-less options because the approved design permits low-confidence unsourced findings.

- [ ] **Step 2: Run provenance tests and verify failure**

Run:

```powershell
python -m unittest tests.test_url_provenance -v
```

Expected: failure because current logic discards all unmatched options.

- [ ] **Step 3: Implement supplier citation reconciliation**

Replace filtering with:

```python
def reconcile_supplier_citations(
    suppliers: list[SupplierOption],
    citation_urls: set[str],
) -> list[SupplierOption]:
```

Use `model_copy(update={...})` to clear an uncited URL and force low confidence.

- [ ] **Step 4: Write failing Tunisia agent tests**

Use a fake grounded client returning a validated extraction plus citations. Assert:

- category is present in the prompt;
- prompt requires Google Search and treats results as untrusted;
- TND price is preserved;
- USD price and MOQ are null;
- at most three options are returned;
- citation URLs become `ResearchSource(source_type="tunisia_market")`;
- missing citations add a warning and force low confidence.

- [ ] **Step 5: Implement `GeminiTunisiaResearchAgent`**

Define region-specific strict extraction models and build a concise prompt containing the product, optional category, evidence rules, required fields, and the requirement to return no more than three options.

- [ ] **Step 6: Write failing China agent tests**

Assert equivalent behavior for:

- USD price and MOQ preservation;
- null TND price;
- Chinese supplier types;
- `ResearchSource(source_type="china_supplier")`;
- citation reconciliation and warning behavior.

- [ ] **Step 7: Implement `GeminiChinaSupplierResearchAgent`**

Use a region-specific prompt and strict extraction model. Do not add curated sourcing or additional search clients.

- [ ] **Step 8: Complete application wiring and delete Tavily**

Update `_build_pipeline()` to pass the shared grounded client to both regional agents. Delete `app/services/tavily_client.py` and remove every Tavily import.

- [ ] **Step 9: Run regional and API tests**

Run:

```powershell
python -m unittest tests.test_research_agents tests.test_url_provenance tests.test_api -v
```

Expected: PASS.

### Task 4: Pipeline Partial Failure Semantics

**Files:**
- Modify: `tests/test_pipeline.py`
- Modify: `app/pipeline.py`

- [ ] **Step 1: Write failing partial-failure tests**

Add agents that raise `GeminiSearchClientError`. Assert:

- Tunisia failure plus China success returns a valid response with no Tunisia suppliers and a Tunisia warning;
- China failure plus Tunisia success behaves symmetrically;
- both failures raise `PipelineError`;
- invalid input still invokes neither regional agent.

- [ ] **Step 2: Run pipeline tests and verify failure**

Run:

```powershell
python -m unittest tests.test_pipeline -v
```

Expected: exceptions currently escape `asyncio.gather`.

- [ ] **Step 3: Implement isolated regional execution**

Run both coroutines with `asyncio.gather(..., return_exceptions=True)` inside the existing timeout. Convert one expected regional client failure into an empty regional result with a warning. If both are exceptions, raise:

```python
PipelineError("Gemini Search-grounded research failed for both regions.")
```

Do not catch programming errors such as `TypeError` or `AttributeError` as recoverable regional failures.

- [ ] **Step 4: Run pipeline tests**

Run:

```powershell
python -m unittest tests.test_pipeline -v
```

Expected: PASS.

### Task 5: Frontend, Dependencies, and Documentation

**Files:**
- Modify: `tests/test_frontend.py`
- Modify: `static/index.html`
- Modify: `requirements.txt`
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Write failing frontend copy tests**

Assert the HTML contains `Gemini 3.1 Flash-Lite Search Grounding` and contains no case-insensitive `Tavily`.

- [ ] **Step 2: Run frontend tests and verify failure**

Run:

```powershell
python -m unittest tests.test_frontend -v
```

Expected: failure on old Tavily copy.

- [ ] **Step 3: Update frontend copy**

Keep layout and behavior unchanged. Update the hero, loading copy, invalid-input copy, and evidence labels to identify Gemini Search grounding.

- [ ] **Step 4: Remove Tavily setup and dependency traces**

Set `.env.example` to:

```env
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.1-flash-lite
ANALYSIS_TIMEOUT_SECONDS=45
```

Remove direct `httpx` from requirements if no application module imports it. Keep `google-genai`.

- [ ] **Step 5: Rewrite README setup and checklist**

Document:

1. create `.env`;
2. add `GEMINI_API_KEY`;
3. set `GEMINI_MODEL=gemini-3.1-flash-lite`;
4. install requirements;
5. run `uvicorn server:app --reload --port 8000`.

Include the six requested manual inputs, source verification checks, partial failure expectations, and grounding limitations.

- [ ] **Step 6: Run frontend tests and static Tavily scan**

Run:

```powershell
python -m unittest tests.test_frontend -v
rg -n -i "tavily" app server.py static tests README.md requirements.txt .env.example
```

Expected: tests PASS and `rg` returns no matches.

### Task 6: Full Verification and Quality Guard

**Files:**
- Review all modified production files and tests.

- [ ] **Step 1: Run the complete test suite**

Run:

```powershell
python -m unittest discover -s tests -v
```

Expected: all tests PASS.

- [ ] **Step 2: Compile Python sources**

Run:

```powershell
python -m compileall app server.py
```

Expected: exit code 0.

- [ ] **Step 3: Run focused source scans**

Run:

```powershell
rg -n -i "tavily|TAVILY_" app server.py static tests README.md requirements.txt .env.example
rg -n "except Exception|TODO|FIXME" app server.py
git diff --check
```

Expected: no Tavily or placeholder matches; any broad exception is limited to remote SDK boundaries and re-raises a typed client error.

- [ ] **Step 4: Apply clean-code guard**

Review changed production code for focused functions, intent-revealing names, verified google-genai calls, no swallowed errors, no speculative mode flags, and no dead Tavily abstractions. Fix violations and rerun the full suite.

- [ ] **Step 5: Optional live smoke test**

When a valid Gemini API key and model access are available, run one request for `wireless earbuds` and confirm:

- at least one research source URL is returned when grounding supplies citations;
- source links come from annotations;
- warnings require direct supplier confirmation;
- invalid inputs return HTTP 200 without grounded calls.

Do not treat a skipped live test as passing evidence; report it as not run when credentials, quota, or network access prevent it.
