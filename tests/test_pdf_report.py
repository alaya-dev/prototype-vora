import base64
from datetime import date
from pathlib import Path
import unittest

from app.prototype.schemas import PrototypeAnalyzeResponse, SourceReference
from app.services.pdf_report import build_opportunity_pdf, opportunity_pdf_filename
from app.schemas import ProductUnderstanding


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
            sources=[SourceReference(title="Tomobile Store", url="https://example.com/source", data_used="Retail price")],
        )

        pdf = build_opportunity_pdf(report, "fr")

        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertIn(b"/URI", pdf)
        self.assertEqual(
            opportunity_pdf_filename(report, date(2026, 8, 23)),
            "NEXORA_Analyse_Huile_moteur_5W30_4L_2026-08-23.pdf",
        )
