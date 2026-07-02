from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.prototype.schemas import (
    AnalyticsRunDetail,
    AnalyticsRunSummary,
    AnalyticsSummary,
    ContactEnrichmentMetrics,
    ContactSellerCard,
    CostConfig,
    PrototypeRevealResponse,
    PrototypeSourcingLink,
    SourcingAgent,
)


class PrototypeStore:
    def __init__(self, db_path: str | Path = "data/vora_prototype.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS prototype_runs (
                    run_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    product_input TEXT NOT NULL,
                    normalized_product TEXT NOT NULL,
                    status TEXT NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    warnings_json TEXT NOT NULL,
                    errors_json TEXT NOT NULL,
                    product_understanding_json TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    hidden_links_json TEXT NOT NULL,
                    contact_metrics_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS provider_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    evidence_group TEXT NOT NULL,
                    status TEXT NOT NULL,
                    api_calls INTEGER NOT NULL,
                    raw_sources_count INTEGER NOT NULL,
                    latency_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS api_usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    service TEXT NOT NULL,
                    calls INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cost_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    data_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sourcing_agents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL DEFAULT '',
                    company_name TEXT NOT NULL DEFAULT '',
                    country_or_region TEXT NOT NULL DEFAULT '',
                    email TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '',
                    whatsapp TEXT NOT NULL DEFAULT '',
                    website TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1
                );
                """
            )
            _ensure_column(connection, "prototype_runs", "contact_metrics_json", "TEXT NOT NULL DEFAULT '{}'")

    def save_cost_config(self, config: CostConfig) -> CostConfig:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO cost_config (id, data_json) VALUES (1, ?)
                ON CONFLICT(id) DO UPDATE SET data_json = excluded.data_json
                """,
                (json.dumps(config.model_dump()),),
            )
        return config

    def get_cost_config(self) -> CostConfig:
        with self._connection() as connection:
            row = connection.execute("SELECT data_json FROM cost_config WHERE id = 1").fetchone()
        if row is None:
            return CostConfig()
        return CostConfig.model_validate(json.loads(row["data_json"]))

    def create_run(
        self,
        product_input: str,
        normalized_product: str,
        status: str,
        latency_ms: int,
        warnings: list[str],
        errors: list[str],
        product_understanding: dict | None = None,
        response: dict | None = None,
        hidden_links: dict | None = None,
        run_id: str | None = None,
    ) -> str:
        run_id = run_id or f"run_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO prototype_runs (
                    run_id, timestamp, product_input, normalized_product, status,
                    latency_ms, warnings_json, errors_json, product_understanding_json,
                    response_json, hidden_links_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    datetime.now(timezone.utc).isoformat(),
                    product_input,
                    normalized_product,
                    status,
                    latency_ms,
                    json.dumps(warnings),
                    json.dumps(errors),
                    json.dumps(product_understanding or {}),
                    json.dumps(response or {}),
                    json.dumps(hidden_links or {}),
                ),
            )
        return run_id

    def update_run_payload(
        self,
        run_id: str,
        status: str,
        latency_ms: int,
        warnings: list[str],
        errors: list[str],
        response: dict,
        hidden_links: dict,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE prototype_runs
                SET status = ?, latency_ms = ?, warnings_json = ?, errors_json = ?,
                    response_json = ?, hidden_links_json = ?
                WHERE run_id = ?
                """,
                (
                    status,
                    latency_ms,
                    json.dumps(warnings),
                    json.dumps(errors),
                    json.dumps(response),
                    json.dumps(hidden_links),
                    run_id,
                ),
            )

    def update_hidden_links(self, run_id: str, hidden_links: dict) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE prototype_runs SET hidden_links_json = ? WHERE run_id = ?",
                (json.dumps(hidden_links), run_id),
            )

    def update_contact_enrichment_metrics(
        self,
        run_id: str,
        metrics: ContactEnrichmentMetrics,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE prototype_runs SET contact_metrics_json = ? WHERE run_id = ?",
                (json.dumps(metrics.model_dump()), run_id),
            )

    def log_provider_attempt(
        self,
        run_id: str,
        provider_id: str,
        evidence_group: str,
        status: str,
        api_calls: int,
        raw_sources_count: int,
        latency_ms: int,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO provider_attempts
                    (run_id, provider_id, evidence_group, status, api_calls, raw_sources_count, latency_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, provider_id, evidence_group, status, api_calls, raw_sources_count, latency_ms),
            )

    def log_api_usage(self, run_id: str, service: str, calls: int) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO api_usage_events (run_id, service, calls) VALUES (?, ?, ?)",
                (run_id, service, calls),
            )

    def get_run_detail(self, run_id: str) -> AnalyticsRunDetail:
        with self._connection() as connection:
            run = connection.execute("SELECT * FROM prototype_runs WHERE run_id = ?", (run_id,)).fetchone()
            attempts = connection.execute(
                "SELECT provider_id, evidence_group, status, api_calls, raw_sources_count, latency_ms FROM provider_attempts WHERE run_id = ?",
                (run_id,),
            ).fetchall()
            usage = connection.execute(
                "SELECT service, calls FROM api_usage_events WHERE run_id = ?",
                (run_id,),
            ).fetchall()
        if run is None:
            raise KeyError(run_id)
        return self._build_run_detail(run, attempts, usage)

    def list_runs(self) -> list[AnalyticsRunSummary]:
        with self._connection() as connection:
            runs = connection.execute("SELECT * FROM prototype_runs ORDER BY timestamp DESC").fetchall()
            attempts = connection.execute(
                "SELECT run_id, provider_id, evidence_group, status, api_calls, raw_sources_count, latency_ms FROM provider_attempts"
            ).fetchall()
            usage = connection.execute("SELECT run_id, service, calls FROM api_usage_events").fetchall()
        attempts_by_run = _group_rows(attempts, "run_id")
        usage_by_run = _group_rows(usage, "run_id")
        summaries: list[AnalyticsRunSummary] = []
        for run in runs:
            detail = self._build_run_detail(
                run,
                attempts_by_run.get(run["run_id"], []),
                usage_by_run.get(run["run_id"], []),
            )
            summary_data = detail.model_dump()
            summary_data.pop("provider_attempts", None)
            summary_data.pop("api_usage_events", None)
            summary_data.pop("hidden_links", None)
            summaries.append(AnalyticsRunSummary.model_validate(summary_data))
        return summaries

    def get_summary(self) -> AnalyticsSummary:
        runs = self.list_runs()
        provider_counts: dict[str, int] = {}
        for run in runs:
            detail = self.get_run_detail(run.run_id)
            for attempt in detail.provider_attempts:
                provider_counts[attempt["provider_id"]] = provider_counts.get(attempt["provider_id"], 0) + attempt["api_calls"]
        latency_values = [run.latency_ms for run in runs]
        return AnalyticsSummary(
            total_runs=len(runs),
            total_estimated_research_cost_usd=round(sum(run.estimated_research_cost_usd for run in runs), 4),
            average_latency_ms=round(sum(latency_values) / len(latency_values), 2) if latency_values else 0.0,
            provider_call_counts=provider_counts,
        )

    def upsert_sourcing_agent(self, payload: dict[str, Any], agent_id: int | None = None) -> int:
        agent = SourcingAgent.model_validate({"id": agent_id or 0, **payload})
        with self._connection() as connection:
            if agent_id is None:
                duplicate_id = _find_duplicate_agent_id(connection, agent)
                if duplicate_id is not None:
                    return duplicate_id
                cursor = connection.execute(
                    """
                    INSERT INTO sourcing_agents
                        (name, company_name, country_or_region, email, phone, whatsapp, website, notes, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _agent_values(agent),
                )
                return int(cursor.lastrowid)
            connection.execute(
                """
                UPDATE sourcing_agents
                SET name = ?, company_name = ?, country_or_region = ?, email = ?,
                    phone = ?, whatsapp = ?, website = ?, notes = ?, active = ?
                WHERE id = ?
                """,
                (*_agent_values(agent), agent_id),
            )
        return agent_id

    def list_sourcing_agents(self, active_only: bool = False) -> list[SourcingAgent]:
        query = "SELECT * FROM sourcing_agents"
        params: tuple = ()
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY id"
        with self._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return _dedupe_agents([_agent_from_row(row) for row in rows])

    def delete_sourcing_agent(self, agent_id: int) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM sourcing_agents WHERE id = ?", (agent_id,))

    def get_reveal(self, run_id: str) -> PrototypeRevealResponse:
        with self._connection() as connection:
            run = connection.execute("SELECT hidden_links_json FROM prototype_runs WHERE run_id = ?", (run_id,)).fetchone()
        if run is None:
            raise KeyError(run_id)
        hidden = json.loads(run["hidden_links_json"] or "{}")
        return PrototypeRevealResponse(
            run_id=run_id,
            china_sourcing_links=[],
            tunisia_sourcing_links=[
                PrototypeSourcingLink.model_validate(link)
                for link in hidden.get("tunisia_sourcing_links", [])
            ],
            seller_contacts=[
                ContactSellerCard.model_validate(contact)
                for contact in hidden.get("seller_contacts", [])
                if _has_usable_contact_dict(contact)
            ],
            sourcing_agents=self.list_sourcing_agents(active_only=True),
        )

    def get_hidden_links(self, run_id: str) -> dict:
        with self._connection() as connection:
            run = connection.execute("SELECT hidden_links_json FROM prototype_runs WHERE run_id = ?", (run_id,)).fetchone()
        if run is None:
            raise KeyError(run_id)
        return json.loads(run["hidden_links_json"] or "{}")

    def _build_run_detail(self, run, attempts, usage) -> AnalyticsRunDetail:
        warnings = json.loads(run["warnings_json"] or "[]")
        errors = json.loads(run["errors_json"] or "[]")
        attempts_list = [dict(row) for row in attempts]
        usage_list = [dict(row) for row in usage]
        response = json.loads(run["response_json"] or "{}")
        hidden_links = json.loads(run["hidden_links_json"] or "{}")
        contact_metrics = json.loads(run["contact_metrics_json"] or "{}")
        retail_debug = hidden_links.get("retail_evidence_debug") or {}
        image_debug = hidden_links.get("product_image_debug") or {}
        provider_ids = [attempt["provider_id"] for attempt in attempts_list]
        raw_sources = sum(int(attempt["raw_sources_count"]) for attempt in attempts_list)
        provider_calls = sum(int(attempt["api_calls"]) for attempt in attempts_list)
        gemini_intent_calls = sum(event["calls"] for event in usage_list if event["service"] == "gemini_intent")
        gemini_analysis_calls = sum(event["calls"] for event in usage_list if event["service"] == "gemini_analysis")
        contact_attempts = [attempt for attempt in attempts_list if attempt["evidence_group"] == "contact_enrichment"]
        contact_search_api_calls = sum(int(attempt["api_calls"]) for attempt in contact_attempts)
        contact_cost = _estimate_cost(contact_attempts, [], self.get_cost_config())
        profit = response.get("profitability_estimate") or {}
        sourcing_summary = response.get("sourcing_summary") or {}
        china_links = hidden_links.get("china_sourcing_links", []) or []
        tunisia_links = hidden_links.get("tunisia_sourcing_links", []) or []
        source_unit_price = profit.get("source_unit_price_tnd")
        if source_unit_price is None:
            source_unit_price = sourcing_summary.get("china_price_min_tnd_estimate")
        landed_cost = profit.get("estimated_landed_cost_per_unit_tnd")
        if landed_cost is None:
            landed_cost = profit.get("estimated_source_cost_tnd")
        landed_notes = profit.get("landed_cost_breakdown_notes", "")
        if landed_cost is not None and not landed_notes:
            landed_notes = "Legacy run did not store a landed cost breakdown."
        return AnalyticsRunDetail(
            run_id=run["run_id"],
            timestamp=run["timestamp"],
            product_input=run["product_input"],
            normalized_product=run["normalized_product"],
            provider_fallback_path=list(dict.fromkeys(provider_ids)),
            firecrawl_called="firecrawl" in provider_ids,
            tavily_called="tavily" in provider_ids,
            exa_called="exa" in provider_ids,
            gemini_intent_calls=gemini_intent_calls,
            gemini_analysis_calls=gemini_analysis_calls,
            provider_api_calls=provider_calls,
            raw_sources_collected=raw_sources,
            sources_used_in_final_analysis=raw_sources,
            latency_ms=run["latency_ms"],
            status=run["status"],
            warnings=warnings,
            errors=errors,
            estimated_research_cost_usd=_estimate_cost(attempts_list, usage_list, self.get_cost_config()),
            contact_enrichment_called=bool(contact_attempts or contact_metrics),
            contact_provider_attempts=len(contact_attempts),
            contact_search_api_calls=contact_search_api_calls,
            contacts_found_count=contact_metrics.get("contacts_found_count", 0),
            contacts_with_email_count=contact_metrics.get("contacts_with_email_count", 0),
            contacts_with_whatsapp_count=contact_metrics.get("contacts_with_whatsapp_count", 0),
            contact_enrichment_latency=contact_metrics.get("contact_enrichment_latency", 0),
            contact_enrichment_estimated_cost=contact_cost,
            contact_enrichment_status=contact_metrics.get("contact_enrichment_status", "not_found"),
            contact_enrichment_reason=contact_metrics.get("contact_enrichment_reason", ""),
            contact_cards_rejected_count=contact_metrics.get("contact_cards_rejected_count", 0),
            contact_rejection_reasons=contact_metrics.get("contact_rejection_reasons", []),
            usable_contacts_found_count=contact_metrics.get("usable_contacts_found_count", contact_metrics.get("contacts_found_count", 0)),
            was_product_image_found=bool(response.get("product_image_url")),
            product_image_source_url=response.get("product_image_source_url"),
            product_image_candidates_count=image_debug.get("product_image_candidates_count", 0),
            product_image_selected_source=image_debug.get("product_image_selected_source"),
            product_image_rejection_reasons=image_debug.get("product_image_rejection_reasons", []),
            source_unit_price_tnd=source_unit_price,
            estimated_landed_cost_per_unit_tnd=landed_cost,
            landed_cost_breakdown_notes=landed_notes,
            estimated_meta_campaign_budget_tnd=profit.get("estimated_meta_campaign_budget_tnd"),
            expected_units_sold_from_campaign=profit.get("expected_units_sold_from_campaign"),
            estimated_ad_cost_per_sold_unit_tnd=profit.get("estimated_ad_cost_per_sold_unit_tnd"),
            hidden_sourcing_urls_count=len([link for link in [*china_links, *tunisia_links] if link.get("url")]),
            selected_sourcing_offers_count=len(china_links) + len(tunisia_links),
            retail_candidate_sources_before_cap=retail_debug.get("retail_candidate_sources_before_cap", 0),
            retail_candidate_sources_after_cap=retail_debug.get("retail_candidate_sources_after_cap", 0),
            dropped_retail_sources=retail_debug.get("dropped_retail_sources", 0),
            known_tunisian_retail_domains_found=retail_debug.get("known_tunisian_retail_domains_found", []),
            provider_attempts=attempts_list,
            api_usage_events=usage_list,
            hidden_links=hidden_links,
        )


def _estimate_cost(attempts: list[dict], usage: list[dict], config: CostConfig) -> float:
    provider_costs = {
        "firecrawl": config.firecrawl_cost_per_call,
        "tavily": config.tavily_cost_per_call,
        "exa": config.exa_cost_per_call,
    }
    total = sum(
        attempt["api_calls"] * provider_costs.get(attempt["provider_id"], 0.0)
        for attempt in attempts
    )
    total += sum(
        event["calls"]
        * (
            config.gemini_intent_cost_per_call
            if event["service"] == "gemini_intent"
            else config.gemini_analysis_cost_per_call
            if event["service"] == "gemini_analysis"
            else 0.0
        )
        for event in usage
    )
    return round(total, 4)


def _agent_values(agent: SourcingAgent) -> tuple:
    return (
        agent.name,
        agent.company_name,
        agent.country_or_region,
        agent.email,
        agent.phone,
        agent.whatsapp,
        agent.website,
        agent.notes,
        1 if agent.active else 0,
    )


def _agent_from_row(row) -> SourcingAgent:
    return SourcingAgent(
        id=row["id"],
        name=row["name"],
        company_name=row["company_name"],
        country_or_region=row["country_or_region"],
        email=row["email"],
        phone=row["phone"],
        whatsapp=row["whatsapp"],
        website=row["website"],
        notes=row["notes"],
        active=bool(row["active"]),
    )


def _find_duplicate_agent_id(connection: sqlite3.Connection, agent: SourcingAgent) -> int | None:
    key = _agent_dedupe_key(agent)
    if key is None:
        return None
    rows = connection.execute("SELECT * FROM sourcing_agents ORDER BY id").fetchall()
    for row in rows:
        existing = _agent_from_row(row)
        if _agent_dedupe_key(existing) == key:
            return existing.id
    return None


def _dedupe_agents(agents: list[SourcingAgent]) -> list[SourcingAgent]:
    seen: set[str] = set()
    deduped: list[SourcingAgent] = []
    for agent in agents:
        key = _agent_dedupe_key(agent) or f"id:{agent.id}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(agent)
    return deduped


def _agent_dedupe_key(agent: SourcingAgent) -> str | None:
    email = agent.email.strip().lower()
    if email:
        return f"email:{email}"
    phone = _normalize_phone(agent.phone or agent.whatsapp)
    name = re.sub(r"\s+", " ", agent.name.strip().lower())
    if name and phone:
        return f"name_phone:{name}:{phone}"
    return None


def _normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def _has_usable_contact_dict(contact: dict) -> bool:
    return bool(
        contact.get("email")
        or contact.get("phone")
        or contact.get("whatsapp")
        or contact.get("contact_page_url")
        or contact.get("website")
    )


def _group_rows(rows, key: str) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for row in rows:
        grouped.setdefault(row[key], []).append(row)
    return grouped


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
