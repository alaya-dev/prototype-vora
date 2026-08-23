import base64
from datetime import date
from pathlib import Path
import unittest
from io import BytesIO

from app.prototype.schemas import (
    ComparabilityAssessment,
    DetailedScoring,
    ProfitabilityEstimate,
    PrototypeAnalyzeResponse,
    RetailOfferView,
    ScoreCriterion,
    SourceReference,
)
from app.services.pdf_report import build_opportunity_pdf, opportunity_pdf_filename
from app.schemas import ProductUnderstanding
from pypdf import PdfReader


class PdfReportTests(unittest.TestCase):
    def test_pdf_embeds_existing_dashboard_image_and_source_link(self) -> None:
        logo_bytes = Path("logo/Nexora_logo_transparent_clean_cropped.png").read_bytes()
        image_data_url = "data:image/png;base64," + base64.b64encode(logo_bytes).decode()
        report = PrototypeAnalyzeResponse(
            run_id="run-pdf",
            product_understanding=ProductUnderstanding(
                original_product="Huile moteur 5W-30 4L",
                normalized_product="5W-30 engine oil 4L",
                product_category="Automotive fluids",
                technical_specs=["5W-30", "4L"],
            ),
            product_image_url=image_data_url,
            product_description="Huile moteur pour analyse de compatibilité.",
            retail_offers=[
                RetailOfferView(
                    seller_name="Tomobile Store",
                    product_title="Huile moteur 5W-30 4L",
                    volume_text="4L",
                    price_tnd=120,
                    source_url="https://example.com/source",
                ),
            ],
            sources=[SourceReference(title="Tomobile Store", url="https://example.com/source", data_used="Retail price")],
        )

        pdf = build_opportunity_pdf(report, "fr")

        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertIn(b"/URI", pdf)
        self.assertEqual(
            opportunity_pdf_filename(report, date(2026, 8, 23)),
            "NEXORA_Analyse_Huile_moteur_5W30_4L_2026-08-23.pdf",
        )

    def test_pdf_embeds_existing_svg_dashboard_image(self) -> None:
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="160"><rect width="240" height="160" fill="#164698"/></svg>'
        image_data_url = "data:image/svg+xml," + svg
        report = PrototypeAnalyzeResponse(
            run_id="run-svg",
            product_understanding=ProductUnderstanding(original_product="Huile moteur 5W-30 4L"),
            product_image_url=image_data_url,
        )

        text = "\\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(build_opportunity_pdf(report, "fr"))).pages)

        self.assertNotIn("Image produit non disponible", text)

    def test_pdf_normalizes_market_prices_filters_irrelevant_sources_and_qualifies_go(self) -> None:
        report = PrototypeAnalyzeResponse(
            run_id="run-normalized",
            target_market="Tunisia",
            sourcing_country="China",
            product_understanding=ProductUnderstanding(
                original_product="Huile moteur 5W-30 4L",
                normalized_product="5W-30 engine oil 4L",
                product_category="Automotive Fluids",
            ),
            comparability=ComparabilityAssessment(level="medium", score=62),
            detailed_scoring=DetailedScoring(total=69, criteria=[ScoreCriterion(key="risk", score=5, max_score=5)]),
            recommendation="go",
            decision_scores={"confidence": "medium", "go_percent": 69, "no_go_percent": 31},
            profitability_estimate=ProfitabilityEstimate(
                source_unit_price_tnd=6.2,
                estimated_landed_cost_per_unit_tnd=12.82,
                digital_ad_budget_default_tnd=400,
            ),
            retail_offers=[
                RetailOfferView(seller_name="Mannol", product_title="Mannol 4L", volume_text="4L", price_tnd=134.9, source_url="https://example.com/mannol"),
                RetailOfferView(seller_name="Shell", product_title="Shell 5L", volume_text="5L", price_tnd=159, source_url="https://example.com/shell"),
            ],
            sources=[
                SourceReference(title="Mannol market price", url="https://example.com/mannol", data_used="Tunisia retail price"),
                SourceReference(title="Space Heater, 1500W Electric Heaters", url="https://example.com/heater", data_used="Context evidence (china_sourcing)"),
            ],
        )

        text = "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(build_opportunity_pdf(report, "fr"))).pages)

        self.assertIn("33.725 TND/L", text)
        self.assertIn("31.8 TND/L", text)
        self.assertIn("131.05 TND", text)
        self.assertIn("118.23 TND", text)
        self.assertIn("GO SOUS CONDITIONS", text)
        self.assertIn("Maîtrise du risque", text)
        self.assertNotIn("Space Heater", text)
