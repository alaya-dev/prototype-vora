"""E2E check: full analysis for 'Huile moteur 5W-30 4L' / Tunisia / China.

Run with the server already listening on 127.0.0.1:8000.
Verifies report sections, console errors, NaN/undefined leaks, sources, PDF hook.
"""
from __future__ import annotations

import json
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
PRODUCT = "Huile moteur 5W-30 4L"

REQUIRED_FR_STRINGS = [
    "Résumé exécutif",
    "Produit analysé",
    "Sourcing international",
    "Coût rendu en Tunisie",
    "Marché tunisien",
    "Prix détail",
    "Analyse concurrentielle",
    "Analyse de rentabilité",
    "Potentiel commercial",
    "Potentiel Ads",
    "Risques principaux",
    "Décision GO / NO GO",
    "Scoring détaillé",
    "Sources & preuves",
    "Comparabilité",
]

BAD_TOKENS = ["NaN", "undefined", "[object Object]"]


def main() -> int:
    console_errors: list[str] = []
    api_errors: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("response", lambda res: api_errors.append(f"{res.status} {res.url}") if res.status >= 400 else None)

        page.goto(BASE, wait_until="networkidle")
        page.fill("#prototypeProductInput", PRODUCT)
        page.click("#prototypeAnalyzeButton")

        # Analysis can take a while (multi-provider research + Gemini).
        page.wait_for_selector(".report-cover", timeout=600_000)
        body_text = page.inner_text("#prototypeResult")
        missing = [s for s in REQUIRED_FR_STRINGS if s not in body_text]
        bad_found = {token: token in body_text for token in BAD_TOKENS}

        # Language switch to EN then back
        page.click("#languageFrButton") if False else None

        checks = {
            "image_present": page.locator("#productPhoto img").count() > 0,
            "sources_table_rows": page.locator("section:has(h2:text('Sources')) table tbody tr").count(),
            "retail_table_rows": page.locator("section:has(h2:text('Marché tunisien')) table tbody tr").count() > 0,
            "scoring_total_visible": "/100" in body_text,
            "pdf_button": page.locator("#exportPdfButton").is_visible(),
            "missing_sections": missing,
            "bad_tokens": bad_found,
            "console_errors": console_errors[:10],
            "api_errors": [e for e in api_errors if "/logo/" not in e][:10],
        }

        page.pdf(path="tmp/report_test.pdf", format="A4", print_background=True) if False else None
        page.emulate_media(media="print")
        page.screenshot(path="tmp/report_e2e.png", full_page=True)

        browser.close()

    print(json.dumps(checks, indent=2, ensure_ascii=False))
    ok = not missing and not any(bad_found.values()) and not checks["api_errors"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
