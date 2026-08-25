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
    SourcingOfferView,
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
            china_offers=[
                SourcingOfferView(
                    name="Retained supplier",
                    product_title="Fully Synthetic Automotive Motor Oil 5W30 4L",
                    price_min_tnd=6.2,
                    price_max_tnd=8.06,
                    source_url="https://example.com/supplier",
                    confidence="medium",
                    product_match="exact",
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
            detailed_scoring=DetailedScoring(total=69, criteria=[
                ScoreCriterion(key="market_demand", score=5, max_score=20),
                ScoreCriterion(key="margin", score=20, max_score=20),
                ScoreCriterion(key="sourcing", score=9, max_score=15),
                ScoreCriterion(key="competition", score=14, max_score=15),
                ScoreCriterion(key="ads_potential", score=6, max_score=10),
                ScoreCriterion(key="recurrence", score=8, max_score=10),
                ScoreCriterion(key="differentiation", score=2, max_score=5),
                ScoreCriterion(key="risk", score=5, max_score=5),
            ]),
            recommendation="go",
            decision_scores={"confidence": "medium", "go_percent": 69, "no_go_percent": 31},
            profitability_estimate=ProfitabilityEstimate(
                source_unit_price_tnd=6.2,
                estimated_shipping_per_unit_tnd=4,
                estimated_customs_per_unit_tnd=0.62,
                estimated_handling_per_unit_tnd=0,
                estimated_misc_per_unit_tnd=2,
                estimated_landed_cost_per_unit_tnd=12.82,
                digital_ad_budget_default_tnd=400,
            ),
            china_offers=[SourcingOfferView(
                name="Retained supplier", product_title="5W30 engine oil 4L",
                price_min_tnd=6.2, price_max_tnd=8.06,
                price_unit="4L",
                source_url="https://example.com/supplier", confidence="medium", product_match="exact",
            )],
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
        self.assertIn("À INVESTIGUER", text)
        self.assertIn("Maîtrise du risque", text)
        self.assertNotIn("Space Heater", text)
        for english_fragment in ("seller(s)", "sourcing offer(s)", "Qualitative reading only", "Product looks consumable", "No clear differentiator", "open risk signal"):
            self.assertNotIn(english_fragment, text)

    def test_pdf_recomputes_financials_from_retained_supplier_offer(self) -> None:
        report = PrototypeAnalyzeResponse(
            run_id="run-supplier-truth",
            product_understanding=ProductUnderstanding(original_product="Huile moteur 5W-30 4L"),
            china_offers=[SourcingOfferView(
                name="Retained supplier", product_title="5W30 engine oil 4L",
                price_min_tnd=6.2, price_max_tnd=8.06,
                price_unit=None,
                source_url="https://example.com/supplier", confidence="medium", product_match="exact",
            )],
            retail_offers=[RetailOfferView(
                seller_name="Retail", product_title="Huile moteur 5W-30 4L",
                volume_text="4L", price_tnd=134.9, source_url="https://example.com/retail",
            )],
            profitability_estimate=ProfitabilityEstimate(
                source_unit_price_tnd=1.55,
                estimated_shipping_per_unit_tnd=4,
                estimated_customs_per_unit_tnd=0.15,
                estimated_handling_per_unit_tnd=0,
                estimated_misc_per_unit_tnd=2,
                estimated_landed_cost_per_unit_tnd=7.7,
            ),
        )

        text = "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(build_opportunity_pdf(report, "fr"))).pages)

        self.assertIn("6.2 TND", text)
        self.assertIn("Prix sourcing non directement comparable", text)
        self.assertNotIn("12.82 TND", text)
        self.assertNotIn("1.55 TND", text)

    def test_pdf_normalizes_liter_supplier_price_to_target_package(self) -> None:
        report = PrototypeAnalyzeResponse(
            run_id="run-liter-price",
            product_understanding=ProductUnderstanding(
                original_product="Huile moteur 5W-30 4L",
                normalized_product="5W-30 engine oil 4L",
                technical_specs=["5W-30", "4L"],
            ),
            detailed_scoring=DetailedScoring(criteria=[
                ScoreCriterion(key="margin", score=20, max_score=20),
                ScoreCriterion(key="risk", score=5, max_score=5),
            ]),
            china_offers=[SourcingOfferView(
                name="Retained supplier",
                product_title="5W30 engine oil 4L",
                price_min_tnd=4.65,
                price_max_tnd=6.2,
                price_unit="liter",
                source_url="https://example.com/supplier",
                confidence="low",
                product_match="exact",
            )],
            retail_offers=[
                RetailOfferView(seller_name="Mannol", product_title="Mannol 4L", volume_text="4L", price_tnd=134.9, source_url="https://example.com/mannol"),
                RetailOfferView(seller_name="Shell", product_title="Shell 5L", volume_text="5L", price_tnd=159, source_url="https://example.com/shell"),
            ],
            profitability_estimate=ProfitabilityEstimate(
                source_unit_price_tnd=1.55,
                estimated_shipping_per_unit_tnd=4,
                estimated_customs_per_unit_tnd=0.15,
                estimated_handling_per_unit_tnd=0,
                estimated_misc_per_unit_tnd=2,
                estimated_landed_cost_per_unit_tnd=7.28,
                digital_ad_budget_default_tnd=400,
            ),
        )

        text = "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(build_opportunity_pdf(report, "fr"))).pages)

        self.assertIn("4.65 TND/L", text)
        self.assertIn("18.6 TND", text)
        self.assertIn("26.46 TND", text)
        self.assertNotIn("1.55 TND", text)
        self.assertNotIn("11.12 TND", text)
        self.assertNotIn("7.28 TND", text)
        self.assertIn("Confiance\nFaible", text)

        english_text = "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(build_opportunity_pdf(report, "en"))).pages)

        self.assertIn("Gross margin is about", english_text)
        self.assertIn("Risk control", english_text)
        self.assertNotIn("Marge recalculée", english_text)
        self.assertNotIn("Maîtrise du risque", english_text)

    def test_pdf_uses_retained_four_liter_prices_as_one_comparable_reference(self) -> None:
        report = PrototypeAnalyzeResponse(
            run_id="run-four-liter-retail",
            product_understanding=ProductUnderstanding(
                original_product="Huile moteur 5W-30 4L",
                normalized_product="5W-30 engine oil 4L",
                technical_specs=["5W-30", "4L"],
            ),
            china_offers=[SourcingOfferView(
                name="Retained supplier",
                product_title="5W30 engine oil 4L",
                price_min_tnd=4.65,
                price_max_tnd=6.2,
                price_unit="liter",
                source_url="https://example.com/supplier",
                confidence="medium",
                product_match="exact",
            )],
            retail_offers=[
                RetailOfferView(seller_name="Bestoil Tunisie", product_title="Yacco 5W30 4L", volume_text="4L", price_tnd=117, source_url="https://example.com/yacco"),
                RetailOfferView(seller_name="Tomobile Store", product_title="Mannol 5W30 4L", volume_text="4L", price_tnd=134.9, source_url="https://example.com/mannol"),
            ],
            profitability_estimate=ProfitabilityEstimate(
                source_unit_price_tnd=18.6,
                estimated_shipping_per_unit_tnd=4,
                estimated_customs_per_unit_tnd=1.86,
                estimated_handling_per_unit_tnd=0,
                estimated_misc_per_unit_tnd=2,
                estimated_landed_cost_per_unit_tnd=26.46,
            ),
        )

        text = "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(build_opportunity_pdf(report, "en"))).pages)

        self.assertIn("29.25 TND/L", text)
        self.assertIn("33.725 TND/L", text)
        self.assertIn("125.95 TND", text)
        self.assertIn("99.49 TND", text)
        self.assertIn("79.0%", text)
        self.assertIn("Insufficient data", text)
        self.assertNotIn("503.8 TND", text)

    def test_pdf_replaces_unsupported_retail_range_with_retained_offers(self) -> None:
        report = PrototypeAnalyzeResponse(
            run_id="run-retail-range",
            product_understanding=ProductUnderstanding(original_product="Produit test"),
            product_description="Les prix Tunisie sont compris entre 94 et 219 TND.",
            retail_offers=[
                RetailOfferView(seller_name="Vendeur A", price_tnd=129.9, source_url="https://example.com/a"),
                RetailOfferView(seller_name="Vendeur B", price_tnd=147, source_url="https://example.com/b"),
            ],
        )

        text = "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(build_opportunity_pdf(report, "fr"))).pages)

        self.assertIn("129.9–147 TND", text)
        self.assertNotIn("94", text)
        self.assertNotIn("219", text)
