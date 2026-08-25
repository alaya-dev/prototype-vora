from __future__ import annotations

from base64 import b64decode
from datetime import date
from io import BytesIO
import html
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx
from PIL import Image as PillowImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    LongTable,
    PageBreak,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.utils import ImageReader
from svglib.svglib import svg2rlg
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFError, TTFont

from app.prototype.schemas import PrototypeAnalyzeResponse


ROOT = Path(__file__).resolve().parents[2]
NEXORA_LOGO = ROOT / "logo" / "Nexora_logo_transparent_clean_cropped.png"
NAVY = colors.HexColor("#030927")
BLUE = colors.HexColor("#164698")
CYAN = colors.HexColor("#258090")
TURQUOISE = colors.HexColor("#30AB90")
PALE_BLUE = colors.HexColor("#F3F7FC")
PALE_TURQUOISE = colors.HexColor("#EAF7F3")
MUTED = colors.HexColor("#4C5F82")
LINE = colors.HexColor("#D9E2EF")


def build_opportunity_pdf(report: PrototypeAnalyzeResponse, language: str) -> bytes:
    buffer = BytesIO()
    document = _document(buffer)
    styles = _styles(language)
    story = _build_story(report, language, styles)
    document.build(story, onFirstPage=_draw_page, onLaterPages=_draw_page)
    return buffer.getvalue()


def opportunity_pdf_filename(report: PrototypeAnalyzeResponse, generated_on: date | None = None) -> str:
    product = _product_name(report)
    safe_product = _filename_slug(product) or "Produit"
    report_date = generated_on or date.today()
    return f"NEXORA_Analyse_{safe_product}_{report_date.isoformat()}.pdf"


def _document(buffer: BytesIO):
    from reportlab.platypus import SimpleDocTemplate

    return SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=17 * mm,
        bottomMargin=15 * mm,
        title="NEXORA Product Opportunity Report",
        author="NEXORA",
        subject="Product opportunity pre-study",
    )


def _register_fonts() -> tuple[str, str]:
    font_candidates = [
        (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
    ]
    for regular_path, bold_path in font_candidates:
        if not regular_path.exists() or not bold_path.exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont("NexoraSans", str(regular_path)))
            pdfmetrics.registerFont(TTFont("NexoraSansBold", str(bold_path)))
            return "NexoraSans", "NexoraSansBold"
        except (OSError, TTFError):
            continue
    return "Helvetica", "Helvetica-Bold"


def _styles(language: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    regular_font, bold_font = _register_fonts()
    return {
        "cover_title": ParagraphStyle(
            "CoverTitle", parent=base["Title"], fontName=bold_font, fontSize=22,
            leading=26, textColor=NAVY, spaceAfter=4,
        ),
        "cover_subtitle": ParagraphStyle(
            "CoverSubtitle", parent=base["Normal"], fontName=bold_font, fontSize=9,
            leading=12, textColor=CYAN, spaceAfter=12,
        ),
        "cover_body": ParagraphStyle(
            "CoverBody", parent=base["BodyText"], fontName=regular_font, fontSize=9.5,
            leading=13, textColor=NAVY,
        ),
        "section": ParagraphStyle(
            "Section", parent=base["Heading2"], fontName=bold_font, fontSize=14,
            leading=17, textColor=NAVY, spaceBefore=8, spaceAfter=6, keepWithNext=True,
        ),
        "subsection": ParagraphStyle(
            "Subsection", parent=base["Heading3"], fontName=bold_font, fontSize=10.5,
            leading=13, textColor=BLUE, spaceBefore=7, spaceAfter=4, keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["BodyText"], fontName=regular_font, fontSize=8.6,
            leading=12, textColor=NAVY, spaceAfter=5,
        ),
        "muted": ParagraphStyle(
            "Muted", parent=base["BodyText"], fontName=regular_font, fontSize=7.8,
            leading=10, textColor=MUTED, spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "Small", parent=base["BodyText"], fontName=regular_font, fontSize=7.2,
            leading=9, textColor=NAVY,
        ),
        "table_header": ParagraphStyle(
            "TableHeader", parent=base["BodyText"], fontName=bold_font, fontSize=7,
            leading=8, textColor=colors.white,
        ),
        "table_cell": ParagraphStyle(
            "TableCell", parent=base["BodyText"], fontName=regular_font, fontSize=7.2,
            leading=9, textColor=NAVY,
        ),
        "table_cell_bold": ParagraphStyle(
            "TableCellBold", parent=base["BodyText"], fontName=bold_font, fontSize=7.2,
            leading=9, textColor=NAVY,
        ),
        "kpi_label": ParagraphStyle(
            "KpiLabel", parent=base["BodyText"], fontName=bold_font, fontSize=7,
            leading=8, textColor=MUTED,
        ),
        "kpi_value": ParagraphStyle(
            "KpiValue", parent=base["BodyText"], fontName=bold_font, fontSize=12,
            leading=14, textColor=NAVY,
        ),
        "decision": ParagraphStyle(
            "Decision", parent=base["BodyText"], fontName=bold_font, fontSize=18,
            leading=21, textColor=TURQUOISE, alignment=TA_CENTER,
        ),
        "center": ParagraphStyle(
            "Center", parent=base["BodyText"], fontName=regular_font, fontSize=8,
            leading=10, textColor=MUTED, alignment=TA_CENTER,
        ),
    }


def _build_story(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    story: list[Any] = []
    story.extend(_cover(report, language, styles))
    story.append(PageBreak())
    story.extend(_product_section(report, language, styles))
    story.extend(_sourcing_section(report, language, styles))
    story.extend(_landed_cost_section(report, language, styles))
    story.extend(_market_section(report, language, styles))
    story.extend(_comparability_section(report, language, styles))
    story.extend(_competition_section(report, language, styles))
    story.extend(_profitability_section(report, language, styles))
    story.extend(_commercial_section(report, language, styles))
    story.extend(_ads_section(report, language, styles))
    story.extend(_risks_section(report, language, styles))
    story.extend(_decision_section(report, language, styles))
    story.extend(_sources_section(report, language, styles))
    return story


def _cover(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    labels = _labels(language)
    product = _product_name(report)
    decision = _decision_for_pdf(report, language)
    confidence = _confidence(_global_confidence_key(report), language)
    metadata = [
        [_p(labels["product"], styles["kpi_label"]), _p(product, styles["kpi_value"])],
        [_p(labels["market"], styles["kpi_label"]), _p(_market_name(report.target_market, language), styles["kpi_value"])],
        [_p(labels["date"], styles["kpi_label"]), _p(date.today().isoformat(), styles["kpi_value"])],
        [_p(labels["decision"], styles["kpi_label"]), _p(decision, styles["kpi_value"])],
        [_p(labels["score"], styles["kpi_label"]), _p(f"{_pdf_score_total(report)}/100", styles["kpi_value"])],
        [_p(labels["confidence"], styles["kpi_label"]), _p(confidence, styles["kpi_value"])],
    ]
    metadata_table = Table(metadata, colWidths=[32 * mm, 64 * mm], hAlign="LEFT")
    metadata_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE_BLUE),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    product_image = _product_image(_verified_product_image_url(report), styles, language, _product_name(report))
    summary = _executive_summary(report, language)
    left = [
        Image(str(NEXORA_LOGO), width=46 * mm, height=12 * mm, kind="proportional"),
        Spacer(1, 5),
        _p(labels["report_title"], styles["cover_title"]),
        _p("INTELLIGENT SOURCING. SMARTER GROWTH.", styles["cover_subtitle"]),
        metadata_table,
        Spacer(1, 10),
        _p(labels["summary"], styles["subsection"]),
        _p(_escape(summary or labels["summary_unavailable"]), styles["cover_body"]),
    ]
    right = [product_image, Spacer(1, 5), _p(labels["product_image"], styles["center"])]
    cover_table = Table([[left, right]], colWidths=[112 * mm, 62 * mm], hAlign="LEFT")
    cover_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [cover_table]


def _product_section(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    labels = _labels(language)
    product = report.product_understanding
    rows = [
        (labels["requested_product"], _value(product, "original_product") or _product_name(report)),
        (labels["normalized_product"], _value(product, "normalized_product") or labels["unavailable"]),
        (labels["category"], _category_name(_value(product, "product_category"), language)),
        (labels["variant"], _value(product, "brand_or_model") or labels["unavailable"]),
        (labels["specifications"], ", ".join(_value(product, "technical_specs") or []) or labels["unavailable"]),
        (labels["market"], _market_name(report.target_market, language)),
        (labels["sourcing_country"], _country_name(report.sourcing_country, language)),
    ]
    description = _product_description_for_pdf(report, language)
    return _section(labels["product_section"], [_p(_escape(description), styles["body"])], _key_value_table(rows, styles), styles)


def _sourcing_section(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    labels = _labels(language)
    china_rows = [
        [offer.name or labels["unavailable"], offer.product_title or labels["unavailable"],
         _price_range(offer.price_min, offer.price_max, offer.currency or "USD", labels["unavailable"]),
         _supplier_tnd_conversion(offer, labels["unavailable"]), _supplier_price_unit_label(offer, language),
         _format_moq(offer.moq, language, labels),
         _source_link(offer.source_url, offer.name or labels["source"], styles, language)]
        for offer in report.china_offers
    ]
    wholesale_rows = [
        [offer.name or labels["unavailable"], offer.product_title or labels["unavailable"],
         _tnd_range(offer.price_min_tnd, offer.price_max_tnd, labels["unavailable"]),
         _source_link(offer.source_url, offer.name or labels["source"], styles, language)]
        for offer in report.tunisia_wholesale_offers
    ]
    blocks: list[Any] = []
    blocks.append(_p(labels["international_sourcing"], styles["section"]))
    blocks.append(_p(_confidence_note(_sourcing_confidence_key(report), language), styles["muted"]))
    blocks.append(_p(labels["suppliers"], styles["subsection"]))
    blocks.append(_table(
        [labels["supplier"], labels["product"], labels["price"], labels["tnd_conversion"], labels.get("price_unit", "Price unit"), labels["moq"], labels["source"]],
        china_rows or [[labels["unavailable"]] * 7], [27, 35, 22, 24, 22, 20, 23], styles,
    ))
    blocks.append(_p(labels["wholesale_prices"], styles["subsection"]))
    if wholesale_rows:
        blocks.append(_table([labels["supplier"], labels["product"], labels["price"], labels["source"]], wholesale_rows, [42, 65, 30, 28], styles))
    else:
        blocks.append(_p(labels["no_wholesale"], styles["body"]))
    return blocks


def _landed_cost_section(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    labels = _labels(language)
    financials = _financial_truth(report)
    rows = [[_target_package_cost_label(report, language), _tnd(financials["supplier_price"], labels), _provenance("observed", language)]]
    rows.extend([[_label, _tnd(financials[key], labels), _provenance(provenance, language)] for key, provenance, _label in (
        ("shipping", "estimate", labels["shipping"]), ("customs", "computed", labels["customs"]),
        ("handling", "estimate", labels["handling"]), ("misc", "estimate", labels["misc"]),
    )])
    rows.append([labels["landed_cost"], _tnd(financials["landed_cost"], labels), _provenance("estimate", language)])
    return _section(labels["landed_cost_section"], [_p(_escape(_landed_cost_note(report, language)), styles["muted"])], _table(
        [labels["component"], labels["value"], labels["data_quality"]], rows, [70, 45, 45], styles,
    ), styles)


def _market_section(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    labels = _labels(language)
    retail_rows = [
        [offer.seller_name or labels["unavailable"], offer.brand or labels["unavailable"], offer.product_title or labels["unavailable"],
         offer.volume_text or labels["unavailable"], _tnd_range(offer.price_tnd, offer.price_tnd, labels["unavailable"]) if offer.price_tnd is not None else offer.price_range_tnd or labels["unavailable"],
         _normalized_retail_price(offer, language, labels), offer.city or labels["unavailable"],
         _source_link(offer.source_url, offer.seller_name or labels["source"], styles, language)]
        for offer in report.retail_offers
    ]
    blocks = [_p(labels["market_section"], styles["section"]), _p(labels["retail_prices"], styles["subsection"])]
    blocks.append(_table(
        [labels["seller"], labels["brand"], labels["product"], labels["volume"], labels["price"], labels["normalized"], labels["city"], labels["source"]],
        retail_rows or [[labels["unavailable"]] * 8], [22, 19, 36, 14, 21, 27, 18, 21], styles,
    ))
    blocks.append(_p(labels["wholesale_prices"], styles["subsection"]))
    blocks.append(_p(_escape(labels["wholesale_observed"] if report.tunisia_wholesale_offers else labels["no_wholesale"]), styles["body"]))
    return blocks


def _comparability_section(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    labels = _labels(language)
    level = _level(_comparability_level_key(report), language)
    reasons = _comparability_reasons(report, language)
    normalization = _market_price_basis(report, language)
    body = f"{labels['market_comparability']}: {level}. " + " ".join(reasons) + f" {normalization}"
    return _section(labels["comparability_section"], [_p(_escape(body), styles["body"])], None, styles)


def _comparability_level_key(report: PrototypeAnalyzeResponse) -> str:
    level = report.comparability.level
    if level != "high":
        return level
    target_volume, target_unit = _target_volume(report)
    if not target_volume or not target_unit or not report.retail_offers:
        return "medium"
    observed_volumes = [_volume_value(offer.volume_text or offer.product_title or "") for offer in report.retail_offers]
    if any(volume != target_volume or unit != target_unit for volume, unit in observed_volumes):
        return "medium"
    product_text = _product_comparison_text(report)
    viscosities = re.findall(r"\b\d+w-\d+\b", product_text, re.IGNORECASE)
    if not viscosities or any(not re.search(re.escape(viscosities[0]), offer.product_title or "", re.IGNORECASE) for offer in report.retail_offers):
        return "medium"
    if not re.search(r"\b(api|acea)\b", product_text, re.IGNORECASE):
        return "medium"
    return "high"


def _product_comparison_text(report: PrototypeAnalyzeResponse) -> str:
    product = report.product_understanding
    return " ".join([
        _value(product, "original_product") or "",
        _value(product, "normalized_product") or "",
        " ".join(_value(product, "technical_specs") or []),
        " ".join(offer.product_title or "" for offer in report.retail_offers),
    ])


def _comparability_reasons(report: PrototypeAnalyzeResponse, language: str) -> list[str]:
    if language != "fr":
        return report.comparability.reasons or ["Comparability could not be established."]
    if _comparability_level_key(report) == "high":
        return ["Les produits observés partagent une catégorie et des caractéristiques suffisamment proches."]
    if _comparability_level_key(report) == "medium":
        return ["Les produits sont comparables pour une première lecture, mais les marques, spécifications ou conditionnements diffèrent."]
    return ["Les produits comparés ne sont pas suffisamment équivalents pour soutenir une marge ferme."]


def _competition_section(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    labels = _labels(language)
    brands = ", ".join(sorted({offer.brand for offer in report.retail_offers if offer.brand})) or labels["unavailable"]
    sellers = ", ".join(sorted({offer.seller_name for offer in report.retail_offers if offer.seller_name})) or labels["unavailable"]
    body = f"{labels['competition_level']}: {_competition_display(report, language)}. {labels['brands']}: {brands}. {labels['sellers']}: {sellers}."
    return _section(labels["competition_section"], [_p(_escape(body), styles["body"])], None, styles)


def _profitability_section(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    labels = _labels(language)
    profit = report.profitability_estimate
    financials = _financial_truth(report)
    selling_price = _comparable_market_price(report)
    landed_cost = financials["landed_cost"]
    margin = round(selling_price - landed_cost, 2) if selling_price is not None and landed_cost is not None else None
    quantity = report.analysis_quantity_units
    gross_profit = round(margin * quantity, 2) if margin is not None else None
    ad_budget = profit.digital_ad_budget_default_tnd
    profit_after_ads = round(gross_profit - ad_budget, 2) if gross_profit is not None and ad_budget is not None else None
    rows = [
        [labels["quantity"], str(quantity)],
        [labels["purchase_price"], _supplier_price_display(report, financials["supplier_price"], language, labels)],
        [_target_package_label(language), _target_package_display(report, labels)],
        [_target_package_cost_label(report, language), _tnd(financials["supplier_price"], labels)],
        [labels["landed_cost"], _tnd(landed_cost, labels)],
        [labels["selling_price"], _tnd(selling_price, labels)],
        [labels["gross_margin"], _tnd(margin, labels)],
        [labels["margin_percent"], _margin_percent_values(margin, selling_price)],
        [labels["gross_profit"], _tnd(gross_profit, labels)],
        [labels["ad_budget"], _budget(profit, labels["unavailable"])],
        [labels["profit_after_ads"], _tnd(profit_after_ads, labels)],
    ]
    notes = _profitability_notes(report, language)
    flowables = [_p(labels["profitability_section"], styles["section"]), _p(_market_price_basis(report, language), styles["muted"]), _table([labels["metric"], labels["value"]], rows, [85, 90], styles)]
    if notes:
        flowables.append(_p("<br/>".join(_escape(note) for note in dict.fromkeys(filter(None, notes))), styles["muted"]))
    return flowables


def _commercial_section(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    labels = _labels(language)
    return _section(labels["commercial_section"], [_p(f"{labels['score']}: {report.commercial_potential_score}/100", styles["body"])], None, styles)


def _ads_section(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    labels = _labels(language)
    body = f"{labels['score']}: {report.ads_potential_score}/100. {labels['ads_qualitative']}"
    return _section(labels["ads_section"], [_p(body, styles["body"])], None, styles)


def _risks_section(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    labels = _labels(language)
    content = [_p(f"• {_escape(risk)}", styles["body"]) for risk in _pdf_risks(report, language)] or [_p(labels["unavailable"], styles["body"])]
    return _section(labels["risks_section"], content, None, styles)


def _decision_section(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    labels = _labels(language)
    criteria = _pdf_score_criteria(report, language)
    scores = [[_criterion_label(item.key, language), f"{item.score}/{item.max_score}", _criterion_justification(item, language)] for item in criteria]
    blocks = [_p(labels["decision_section"], styles["section"]), _p(_decision_for_pdf(report, language), styles["decision"]), _p(
        f"{labels['score']}: {_pdf_score_total(report, language)}/100 · {labels['confidence']}: {_confidence(_global_confidence_key(report), language)}", styles["center"],
    )]
    decision_reason = _decision_reason(report, language)
    if decision_reason:
        blocks.append(_p(_escape(decision_reason), styles["body"]))
    blocks.append(_p(labels["scoring"], styles["subsection"]))
    blocks.append(_table([labels["criterion"], labels["score"], labels["justification"]], scores or [[labels["unavailable"]] * 3], [38, 25, 112], styles))
    return blocks


def _pdf_score_criteria(report: PrototypeAnalyzeResponse, language: str = "fr") -> list[Any]:
    criteria = [item.model_copy() for item in report.detailed_scoring.criteria]
    margin = _final_margin(report)
    margin_percent = _margin_percent_number(margin, _comparable_market_price(report))
    for index, item in enumerate(criteria):
        if item.key == "risk":
            score, justification = _pdf_risk_management_score(report, language)
            criteria[index] = item.model_copy(update={"score": score, "justification": justification})
            continue
        if item.key == "margin" and margin is None:
            criteria[index] = item.model_copy(update={
                "score": 0,
                "justification": (
                    "Marge non calculable : l’unité du prix fournisseur n’est pas confirmée."
                    if language == "fr"
                    else "Margin cannot be calculated: the supplier price unit is not confirmed."
                ),
            })
            continue
        if item.key == "sourcing" and not _supplier_price_unit_confirmed(report):
            criteria[index] = item.model_copy(update={
                "score": 3,
                "justification": (
                    "Unité du prix fournisseur non confirmée ; le prix sourcing n’est pas directement comparable."
                    if language == "fr"
                    else "Supplier price unit is not confirmed; the sourcing price is not directly comparable."
                ),
            })
        if item.key == "margin":
            score, penalty = _margin_score_with_confidence(report, margin_percent)
            criteria[index] = item.model_copy(update={
                "score": score,
                "justification": (
                    f"Marge recalculée à partir de l’offre fournisseur retenue : {margin_percent:.1f}%. Pénalité de fiabilité des données : -{penalty} point(s)."
                    if language == "fr"
                    else f"Gross margin is about {margin_percent:.1f}%. Economic score was adjusted by a data reliability penalty of -{penalty} point(s)."
                ),
            })
        if item.key == "competition" and _competition_level_key(report) == "unknown":
            criteria[index] = item.model_copy(update={
                "score": 7,
                "justification": (
                    "Données insuffisantes : moins de trois vendeurs ou concurrents fiables retenus."
                    if language == "fr"
                    else "Insufficient data: fewer than three reliable sellers or competitors were retained."
                ),
            })
    return criteria


def _margin_score_with_confidence(report: PrototypeAnalyzeResponse, margin_percent: float) -> tuple[int, int]:
    base_score = 20 if margin_percent >= 30 else 15 if margin_percent >= 20 else 10 if margin_percent >= 10 else 5 if margin_percent > 0 else 0
    if base_score == 0:
        return 0, 0
    selected = _selected_supplier_offer(report)
    penalty = 0
    if selected and selected.confidence == "low":
        penalty += 2
    if report.landed_cost.partial_estimate:
        penalty += 1
    if not report.tunisia_wholesale_offers:
        penalty += 1
    if _global_confidence_key(report) == "low":
        penalty += 1
    penalty = min(penalty, base_score)
    return base_score - penalty, penalty


def _pdf_score_total(report: PrototypeAnalyzeResponse, language: str = "fr") -> int:
    return min(100, sum(item.score for item in _pdf_score_criteria(report, language)))


def _pdf_risk_management_score(report: PrototypeAnalyzeResponse, language: str = "fr") -> tuple[int, str]:
    score = 5
    limits: list[str] = []
    supplier_count = sum(
        1 for offer in report.china_offers
        if offer.source_url and offer.confidence in {"high", "medium"}
    )
    risk_limits = [
        (_global_confidence_key(report) == "low", 2, "confiance globale faible", "low overall confidence"),
        (not _supplier_price_unit_confirmed(report), 2, "unité du prix fournisseur inconnue", "supplier price unit unknown"),
        (supplier_count < 3, 1, "moins de trois fournisseurs", "fewer than three suppliers"),
        (_competition_level_key(report) == "unknown", 1, "couverture de la concurrence insuffisante", "insufficient competition coverage"),
    ]
    for limited, deduction, label_fr, label_en in risk_limits:
        if limited:
            score -= deduction
            limits.append(label_fr if language == "fr" else label_en)
    if not limits:
        note = "La maîtrise du risque est soutenue par une couverture suffisante des preuves." if language == "fr" else "Risk control is supported by sufficiently complete evidence coverage."
        return score, note
    prefix = "Maîtrise du risque limitée : " if language == "fr" else "Risk control is limited: "
    return max(0, score), prefix + "; ".join(limits) + "."


def _sources_section(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    labels = _labels(language)
    rows = [[_source_link(source.url, _source_display_name(source, labels["source"]), styles, language), _source_data_used(source.data_used, language), _confidence(source.confidence, language)] for source in _relevant_sources(report)]
    return _section(labels["sources_section"], [_p(labels["sources_intro"], styles["muted"])], _table(
        [labels["source"], labels["data_used"], labels["confidence"]], rows or [[labels["unavailable"]] * 3], [80, 70, 25], styles,
    ), styles)


def _section(title: str, intro: list[Any], table: Any, styles: dict[str, ParagraphStyle]) -> list[Any]:
    flowables: list[Any] = [KeepTogether([_p(title, styles["section"]), *intro])]
    if table is not None:
        flowables.append(table)
    return flowables


def _landed_cost_note(report: PrototypeAnalyzeResponse, language: str) -> str:
    components = _financial_truth(report)
    if not _supplier_price_unit_confirmed(report):
        if language == "fr":
            return "Prix fournisseur non comparable : unité non confirmée. Coût rendu et marge non calculés."
        return "Supplier price is not directly comparable because its unit is unconfirmed. Landed cost and margin were not calculated."
    parts = [
        f"{_target_package_cost_label(report, language)} {_tnd(components.get('supplier_price'), _labels(language))}",
        f"{_labels(language)['shipping']} {_tnd(components.get('shipping'), _labels(language))}",
        f"{_labels(language)['customs']} {_tnd(components.get('customs'), _labels(language))}",
        f"{_labels(language)['handling']} {_tnd(components.get('handling'), _labels(language))}",
        f"{_labels(language)['misc']} {_tnd(components.get('misc'), _labels(language))}",
    ]
    if language != "fr":
        return " + ".join(parts) + f" = estimated landed cost {_tnd(components.get('landed_cost'), _labels(language))}. " + _labels(language)["partial_estimate"]
    return " + ".join(parts) + f" = coût rendu estimé {_tnd(components.get('landed_cost'), _labels(language))}. " + _labels(language)["partial_estimate"]


def _profitability_notes(report: PrototypeAnalyzeResponse, language: str) -> list[str]:
    basis = _market_price_basis(report, language)
    if language != "fr":
        return [basis, "Profitability is an estimate, not a guarantee.", "USD/TND rate and logistics charges are configured assumptions."]
    notes = [
        basis,
        "La rentabilité est une estimation et non une garantie.",
        "Le taux USD/TND et les charges logistiques sont des hypothèses configurées.",
        "Le budget publicitaire est un scénario total ; aucun coût par acquisition réel n’est affirmé.",
    ]
    return list(dict.fromkeys(filter(None, notes)))


def _pdf_risks(report: PrototypeAnalyzeResponse, language: str) -> list[str]:
    if language != "fr":
        return list(dict.fromkeys([*report.profitability_estimate.risks, *report.warnings]))
    risks = []
    if not report.tunisia_wholesale_offers:
        risks.append("Aucun prix de gros tunisien public fiable n’a été confirmé.")
    if len(report.china_offers) < 3:
        risks.append("Moins de trois offres Chine avec prix vérifiable ont été retenues.")
    if len(report.retail_offers) < 3:
        risks.append("La couverture des prix détail tunisiens peut être incomplète.")
    if _comparability_level_key(report) in {"low", "unknown"}:
        risks.append("La comparabilité des produits doit être confirmée avant d’utiliser la marge comme argument principal.")
    if report.profitability_estimate.risks:
        risks.append("La qualité, la conformité et les conditions fournisseur doivent être vérifiées avant investissement.")
    return list(dict.fromkeys(risks))


def _decision_reason(report: PrototypeAnalyzeResponse, language: str) -> str:
    margin = _final_margin(report)
    margin_percent = _margin_percent_values(margin, _comparable_market_price(report), language)
    competition = _competition_display(report, language)
    if not _supplier_price_unit_confirmed(report):
        if language == "fr":
            return f"Prix sourcing non directement comparable : l’unité du prix fournisseur n’est pas confirmée. Concurrence : {competition}. Obtenir une offre précisant le prix par bidon 4L ou par unité, confirmer les coûts logistiques et douaniers réels, puis recalculer la marge avant toute décision d’investissement."
        return f"Sourcing price is not directly comparable because the supplier price unit is unconfirmed. Competition: {competition}. Obtain a quote specifying the price per 4L bottle or unit, confirm actual logistics and customs costs, then recalculate the margin before investing."
    if language != "fr":
        return _decision_reason_en(report, margin_percent, competition)
    profitability = (
        "La rentabilité théorique apparaît élevée sur la base des données disponibles."
        if margin is not None and _margin_percent_number(margin, _comparable_market_price(report)) >= 40
        else "La rentabilité reste à confirmer à partir des données disponibles."
    )
    conditions = "Obtenir un devis fournisseur ferme, confirmer les coûts logistiques et douaniers réels, vérifier les normes et la qualité, confirmer les prix de gros tunisiens et valider la demande commerciale."
    return f"{profitability} Marge brute : {margin_percent}. Concurrence : {competition}. {conditions}"


def _decision_reason_en(report: PrototypeAnalyzeResponse, margin_percent: str, competition: str) -> str:
    margin = _final_margin(report)
    profitability = "Theoretical profitability appears high based on the available data." if margin is not None and _margin_percent_number(margin, _comparable_market_price(report)) >= 40 else "Profitability remains to be confirmed from the available data."
    conditions = "Obtain a firm supplier quote, confirm actual logistics and customs costs, verify standards and quality, confirm Tunisian wholesale prices, and validate commercial demand."
    return f"{profitability} Gross margin: {margin_percent}. Competition: {competition}. {conditions}"


def _criterion_justification(item: Any, language: str) -> str:
    if language != "fr":
        if item.key in {"risk", "margin"}:
            return item.justification or "Not available"
        messages = {
            "market_demand": "Seller and price references were observed in Tunisia.",
            "margin": "Gross margin is based on the selling price and estimated landed cost.",
            "sourcing": "Retained sourcing offers; logistics remain to be confirmed.",
            "competition": "Competition is assessed from the number of observed sellers and brands.",
            "ads_potential": "Qualitative reading only; no CPC, CPA, ROAS or search-volume data is invented.",
            "recurrence": "Repurchase potential is inferred from available category signals.",
            "differentiation": "No clear differentiator is documented in the sources.",
        }
        return messages.get(item.key, "Justification unavailable.")
    if item.key == "risk" or (item.key == "margin" and item.score == 0):
        return item.justification or "Justification non disponible."
    messages = {
        "market_demand": "Références de vendeurs et de prix observées en Tunisie.",
        "margin": "Marge brute calculée à partir du prix de vente et du coût rendu estimé.",
        "sourcing": "Offres sourcing retenues ; la logistique reste à confirmer.",
        "competition": "Intensité déduite du nombre de vendeurs et de marques observés.",
        "ads_potential": "Lecture qualitative uniquement, sans CPC, CPA, ROAS ni volume de recherche inventé.",
        "recurrence": "Récurrence déduite des signaux de catégorie disponibles.",
        "differentiation": "Aucun différenciateur clairement documenté dans les sources.",
        "risk": "Risque évalué à partir des limites et avertissements des preuves collectées.",
    }
    return messages.get(item.key, "Justification non disponible.")


def _source_data_used(value: str, language: str) -> str:
    if language != "fr":
        return value or "Not available"
    translations = {
        "China supplier / price / MOQ": "Fournisseur Chine / prix / MOQ",
        "Tunisia wholesale price": "Prix grossiste Tunisie",
        "Tunisia retail price": "Prix détail Tunisie",
        "Context evidence (china_sourcing)": "Contexte sourcing Chine",
        "Context evidence (tunisia_sourcing)": "Contexte grossiste Tunisie",
        "Context evidence (tunisia_retail)": "Contexte marché détail",
    }
    return translations.get(value, "Donnée source") if value else "Non disponible"


def _comparable_market_price(report: PrototypeAnalyzeResponse) -> float | None:
    target_volume, target_unit = _target_volume(report)
    normalized_values = []
    raw_values = []
    for offer in report.retail_offers:
        normalized = _retail_normalized_value(offer)
        volume, unit = _volume_value(offer.volume_text or offer.product_title or "")
        if normalized is not None and unit == target_unit:
            normalized_values.append(normalized)
        if offer.price_tnd is not None:
            raw_values.append(offer.price_tnd)
    if normalized_values and target_volume:
        return round(sum(normalized_values) / len(normalized_values) * target_volume, 2)
    if raw_values:
        return round(sum(raw_values) / len(raw_values), 2)
    return None


def _target_volume(report: PrototypeAnalyzeResponse) -> tuple[float | None, str | None]:
    product = report.product_understanding
    text = " ".join([
        _value(product, "original_product") or "",
        _value(product, "normalized_product") or "",
        " ".join(_value(product, "technical_specs") or []),
    ])
    return _volume_value(text)


def _volume_value(text: str) -> tuple[float | None, str | None]:
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(ml|l|litre?s?|kg|g)\b", text, re.IGNORECASE)
    if not match:
        return None, None
    quantity = float(match.group(1).replace(",", "."))
    unit = match.group(2).lower()
    if unit == "ml":
        return quantity / 1000, "L"
    if unit in {"l", "litre", "litres"}:
        return quantity, "L"
    if unit == "g":
        return quantity / 1000, "kg"
    return quantity, "kg"


def _market_price_basis(report: PrototypeAnalyzeResponse, language: str) -> str:
    labels = _labels(language)
    target_volume, target_unit = _target_volume(report)
    comparable_price = _comparable_market_price(report)
    values = [
        _retail_normalized_value(offer)
        for offer in report.retail_offers
        if _retail_normalized_value(offer) is not None and _volume_value(offer.volume_text or offer.product_title or "")[1] == target_unit
    ]
    if values and target_volume and comparable_price is not None:
        unit = "L" if target_unit == "L" else "kg"
        average = sum(values) / len(values)
        return f"{labels['market_reference']}: {average:.3f} TND/{unit} × {target_volume:g} {unit} = {comparable_price:g} TND."
    return labels["market_reference_unavailable"]


def _margin_percent_values(margin: float | None, selling_price: float | None, language: str = "fr") -> str:
    if margin is None or not selling_price:
        return "Non disponible" if language == "fr" else "Not available"
    return f"{margin / selling_price * 100:.1f}%"


def _margin_percent_number(margin: float | None, selling_price: float | None) -> float:
    if margin is None or not selling_price:
        return 0.0
    return margin / selling_price * 100


def _final_margin(report: PrototypeAnalyzeResponse) -> float | None:
    price = _comparable_market_price(report)
    cost = _financial_truth(report)["landed_cost"]
    return round(price - cost, 2) if price is not None and cost is not None else None


def _source_of_truth_supplier_price(report: PrototypeAnalyzeResponse) -> float | None:
    selected = _selected_supplier_offer(report)
    if selected:
        return _supplier_target_price(report, selected)
    return report.profitability_estimate.source_unit_price_tnd


def _selected_supplier_offer(report: PrototypeAnalyzeResponse) -> Any | None:
    candidates = [offer for offer in report.china_offers if offer.price_min_tnd is not None and offer.source_url]
    exact = [offer for offer in candidates if offer.product_match == "exact"] or candidates
    reliable = [offer for offer in exact if offer.confidence in {"high", "medium"}] or exact
    return min(reliable, key=lambda offer: offer.price_min_tnd) if reliable else None


def _supplier_price_unit_confirmed(report: PrototypeAnalyzeResponse) -> bool:
    offer = _selected_supplier_offer(report)
    return bool(offer and _supplier_price_unit_kind(offer.price_unit))


def _sourcing_confidence_key(report: PrototypeAnalyzeResponse) -> str:
    selected = _selected_supplier_offer(report)
    if selected and selected.confidence == "low":
        return "low"
    if report.sourcing_summary.evidence_confidence == "low":
        return "low"
    return report.sourcing_summary.evidence_confidence or "unknown"


def _supplier_price_unit_kind(price_unit: str | None) -> str | None:
    normalized = re.sub(r"\s+", " ", (price_unit or "").lower()).strip()
    if re.search(r"(?:liter|litre|litres|liters|per l|/l|\bl\b)", normalized):
        return "liter"
    if re.search(r"(?:unit|piece|pcs|bidon|bottle|carton|package)", normalized):
        return "unit"
    if re.fullmatch(r"\d+(?:[.,]\d+)?\s*(?:l|litre?s?)", normalized):
        return "unit"
    return None


def _supplier_target_price(report: PrototypeAnalyzeResponse, offer: Any) -> float | None:
    raw_price = offer.price_min_tnd
    if raw_price is None:
        return None
    if _supplier_price_unit_kind(offer.price_unit) == "liter":
        target_volume, target_unit = _target_volume(report)
        if target_volume and target_unit == "L":
            return round(raw_price * target_volume, 2)
        return None
    if _supplier_price_unit_kind(offer.price_unit) == "unit":
        return raw_price
    return None


def _supplier_price_unit_label(offer: Any, language: str) -> str:
    if not offer.price_unit:
        return "Non déterminée" if language == "fr" else "Not determined"
    unit_kind = _supplier_price_unit_kind(offer.price_unit)
    if unit_kind == "liter":
        return "litre" if language == "fr" else "liter"
    if unit_kind == "unit":
        return "unité" if language == "fr" else "unit"
    return offer.price_unit.strip()


def _supplier_tnd_conversion(offer: Any, unavailable: str) -> str:
    if _supplier_price_unit_kind(offer.price_unit) == "liter":
        return _tnd_range(offer.price_min_tnd, offer.price_max_tnd, unavailable).replace(" TND", " TND/L")
    return _tnd_range(offer.price_min_tnd, offer.price_max_tnd, unavailable)


def _supplier_price_display(report: PrototypeAnalyzeResponse, price: float | None, language: str, labels: dict[str, str]) -> str:
    selected = _selected_supplier_offer(report)
    if selected and _supplier_price_unit_kind(selected.price_unit) == "liter" and selected.price_min_tnd is not None:
        return f"{selected.price_min_tnd:g} TND/L"
    if selected and not _supplier_price_unit_confirmed(report) and selected.price_min_tnd is not None:
        value = _tnd(selected.price_min_tnd, labels)
    else:
        value = _tnd(price, labels)
    if _supplier_price_unit_confirmed(report):
        return value
    suffix = " — unité non déterminée" if language == "fr" else " — unit not determined"
    return value + suffix


def _target_package_label(language: str) -> str:
    return "Conditionnement analysé" if language == "fr" else "Analyzed package"


def _target_package_display(report: PrototypeAnalyzeResponse, labels: dict[str, str]) -> str:
    volume, unit = _target_volume(report)
    if volume is None or unit is None:
        return labels["unavailable"]
    unit_label = "L" if unit == "L" else unit
    return f"{volume:g} {unit_label}"


def _target_package_cost_label(report: PrototypeAnalyzeResponse, language: str) -> str:
    volume, unit = _target_volume(report)
    suffix = f" {volume:g} {unit}" if volume and unit else ""
    base = "Coût produit équivalent" if language == "fr" else "Equivalent product cost"
    return base + suffix


def _financial_truth(report: PrototypeAnalyzeResponse) -> dict[str, float | None]:
    profit = report.profitability_estimate
    supplier_price = _source_of_truth_supplier_price(report)
    if not _supplier_price_unit_confirmed(report):
        return {"supplier_price": supplier_price, "shipping": None, "customs": None, "handling": None, "misc": None, "landed_cost": None}
    shipping = profit.estimated_shipping_per_unit_tnd
    handling = profit.estimated_handling_per_unit_tnd
    misc = profit.estimated_misc_per_unit_tnd
    customs_rate = _customs_rate()
    customs = round(supplier_price * customs_rate, 2) if supplier_price is not None else None
    landed = _sum_known_costs(supplier_price, shipping, customs, handling, misc)
    return {"supplier_price": supplier_price, "shipping": shipping, "customs": customs, "handling": handling, "misc": misc, "landed_cost": landed}


def _customs_rate() -> float:
    return 0.10


def _sum_known_costs(*values: float | None) -> float | None:
    if any(value is None for value in values):
        return None
    return round(sum(value for value in values if value is not None), 2)


def _competition_level_key(report: PrototypeAnalyzeResponse) -> str:
    sellers = {offer.seller_name for offer in report.retail_offers if offer.seller_name}
    brands = {offer.brand for offer in report.retail_offers if offer.brand}
    if len(sellers) < 3 and len(brands) < 3:
        return "unknown"
    if report.competition_level != "unknown":
        return report.competition_level
    competitors = max(len(sellers), len(brands))
    if competitors >= 5:
        return "high"
    if competitors >= 2:
        return "medium"
    return "low" if competitors else "unknown"


def _competition_display(report: PrototypeAnalyzeResponse, language: str) -> str:
    if _competition_level_key(report) == "unknown":
        return "Données insuffisantes" if language == "fr" else "Insufficient data"
    return _level(_competition_level_key(report), language)


def _global_confidence_key(report: PrototypeAnalyzeResponse) -> str:
    if not _supplier_price_unit_confirmed(report):
        return "low"
    supplier_count = sum(1 for offer in report.china_offers if offer.source_url and offer.confidence in {"high", "medium"})
    retail_count = sum(1 for offer in report.retail_offers if offer.source_url and _retail_normalized_value(offer) is not None)
    source_quality = _average_source_quality(report)
    cost_quality = _landed_cost_quality(report)
    comparability_quality = {"high": 1.0, "medium": 0.65, "low": 0.25, "unknown": 0.2}[_comparability_level_key(report)]
    score = (
        min(supplier_count / 3, 1) * 0.25
        + min(retail_count / 3, 1) * 0.20
        + source_quality * 0.20
        + cost_quality * 0.20
        + comparability_quality * 0.15
    )
    if score >= 0.75 and supplier_count >= 3 and retail_count >= 3 and cost_quality >= 0.9 and comparability_quality == 1:
        return "high"
    return "medium" if score >= 0.40 else "low"


def _average_source_quality(report: PrototypeAnalyzeResponse) -> float:
    weights = {"high": 1.0, "medium": 0.65, "low": 0.25, "unknown": 0.2}
    sources = _relevant_sources(report)
    return sum(weights.get(source.confidence, 0.2) for source in sources) / len(sources) if sources else 0.2


def _landed_cost_quality(report: PrototypeAnalyzeResponse) -> float:
    components = report.landed_cost.components
    if not components:
        return 0.2
    known = sum(component.value_tnd is not None for component in components)
    quality = known / len(components)
    return min(quality, 0.6) if report.landed_cost.partial_estimate else quality


def _executive_summary(report: PrototypeAnalyzeResponse, language: str) -> str:
    decision = _decision_for_pdf(report, language)
    score = _pdf_score_total(report)
    market_price = _comparable_market_price(report)
    landed = _financial_truth(report)["landed_cost"]
    margin = round(market_price - landed, 2) if market_price is not None and landed is not None else None
    if language == "fr":
        if market_price is None or landed is None:
            reason = "L’unité du prix fournisseur n’est pas confirmée : le prix sourcing n’est pas directement comparable et la marge n’est pas calculée." if not _supplier_price_unit_confirmed(report) else "Le prix marché comparable ou le coût rendu ne peut pas être confirmé avec les données disponibles."
            return f"La décision finale est {decision} avec un score de {score}/100. {reason}"
        return f"La décision finale est {decision} avec un score de {score}/100. Le prix marché comparable est de {market_price:g} TND pour le conditionnement cible, contre un coût rendu estimé de {landed:g} TND et une marge brute indicative de {margin:g} TND. La décision reste soumise aux vérifications indiquées dans ce rapport."
    if market_price is None or landed is None:
        return f"The final decision is {decision} with a score of {score}/100. Comparable market price or landed cost could not be confirmed from the available data."
    return f"The final decision is {decision} with a score of {score}/100. The comparable market price is {market_price:g} TND for the target package, against an estimated landed cost of {landed:g} TND and an indicative gross margin of {margin:g} TND. The decision remains subject to the verification conditions shown in this report."


def _decision_for_pdf(report: PrototypeAnalyzeResponse, language: str) -> str:
    score = _pdf_score_total(report)
    if not _supplier_price_unit_confirmed(report):
        return "À INVESTIGUER" if language == "fr" else "INVESTIGATE"
    if report.recommendation == "go" and score < 60:
        return "À INVESTIGUER" if language == "fr" else "INVESTIGATE"
    if report.recommendation == "go" and (
        _global_confidence_key(report) != "high"
        or report.landed_cost.partial_estimate
        or _comparability_level_key(report) in {"medium", "low", "unknown"}
    ):
        return "GO SOUS CONDITIONS" if language == "fr" else "GO WITH CONDITIONS"
    return _decision(report.recommendation, language)


def _market_name(value: str, language: str) -> str:
    return "Tunisie" if language == "fr" and value.strip().lower() == "tunisia" else value


def _country_name(value: str, language: str) -> str:
    return "Chine" if language == "fr" and value.strip().lower() == "china" else value


def _category_name(value: str | None, language: str) -> str:
    if not value:
        return "Non disponible" if language == "fr" else "Not available"
    if language == "fr" and value.strip().lower() in {"automotive fluids", "automotive fluid"}:
        return "Fluides automobiles"
    return value


def _format_moq(value: str | None, language: str, labels: dict[str, str]) -> str:
    if not value:
        return labels["unavailable"]
    if language != "fr":
        return value
    match = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(.*)", value.strip())
    if not match:
        return f"{value} — unité non précisée"
    quantity, unit = match.groups()
    translations = {"piece": "pièce", "pieces": "pièces", "pcs": "pièces", "unit": "unité", "units": "unités", "carton": "carton", "cartons": "cartons"}
    return f"{quantity} {translations.get(unit.lower(), unit)}" if unit else f"{quantity} — unité non précisée"


def _relevant_sources(report: PrototypeAnalyzeResponse) -> list[Any]:
    used_urls = {
        offer.source_url for offer in [*report.china_offers, *report.tunisia_wholesale_offers, *report.retail_offers]
        if offer.source_url
    }
    product_text = " ".join([
        _value(report.product_understanding, "original_product") or "",
        _value(report.product_understanding, "normalized_product") or "",
        _value(report.product_understanding, "product_category") or "",
        " ".join(_value(report.product_understanding, "technical_specs") or []),
    ]).lower()
    terms = set(re.findall(r"[a-z0-9]+", product_text))
    if terms.intersection({"huile", "oil", "moteur", "engine", "automotive"}):
        terms.update({"huile", "oil", "moteur", "engine", "motor", "automotive", "lubricant", "5w30"})
    terms = {term for term in terms if len(term) > 2}
    selected, related = [], []
    for source in report.sources:
        if source.url in used_urls:
            selected.append(source)
            continue
        haystack = f"{source.title} {source.url}".lower().replace("-", "").replace(" ", "")
        if any(term.replace("-", "") in haystack for term in terms):
            related.append(source)
    unique = []
    seen_urls = set()
    for source in [*selected, *related]:
        if source.url in seen_urls:
            continue
        seen_urls.add(source.url)
        unique.append(source)
    return unique[:6]


def _normalized_retail_price(offer: Any, language: str, labels: dict[str, str]) -> str:
    normalized = _retail_normalized_value(offer)
    if normalized is not None:
        volume_unit = _volume_value(offer.volume_text or offer.product_title or "")[1]
        if volume_unit:
            return f"{normalized:g} TND/{volume_unit}"
        unit = "unité" if language == "fr" else "unit"
        return f"{normalized:g} TND/{unit}"
    if not offer.normalized_price_text:
        return labels["unavailable"]
    if language == "fr":
        return "Prix normalisé disponible"
    return offer.normalized_price_text


def _retail_normalized_value(offer: Any) -> float | None:
    volume, unit = _volume_value(offer.volume_text or offer.product_title or "")
    if offer.price_tnd is not None and volume and unit in {"L", "kg"}:
        return round(offer.price_tnd / volume, 3)
    return offer.normalized_price_per_unit_tnd


def _table(headers: list[str], rows: list[list[Any]], widths_mm: list[float], styles: dict[str, ParagraphStyle]) -> LongTable:
    header_row = [_p(header, styles["table_header"]) for header in headers]
    converted_rows = [[cell if hasattr(cell, "wrap") else _p(_escape(cell), styles["table_cell"]) for cell in row] for row in rows]
    table = LongTable([header_row, *converted_rows], colWidths=[width * mm for width in widths_mm], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE_BLUE]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _key_value_table(rows: list[tuple[str, str]], styles: dict[str, ParagraphStyle]) -> Table:
    table = Table([[_p(_escape(label), styles["table_header"]), _p(_escape(value), styles["table_cell"])] for label, value in rows], colWidths=[45 * mm, 130 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), BLUE),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
        ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, PALE_BLUE]),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _product_image(url: str | None, styles: dict[str, ParagraphStyle], language: str, product_label: str = "Produit") -> Any:
    try:
        raw = _read_image_source(url) if url else None
    except (OSError, ValueError, httpx.HTTPError):
        raw = None
    if raw and _is_svg(raw):
        try:
            drawing = svg2rlg(BytesIO(raw))
        except (OSError, ValueError, TypeError):
            drawing = None
        if drawing and drawing.width and drawing.height:
            max_width, max_height = 55 * mm, 78 * mm
            scale = min(max_width / drawing.width, max_height / drawing.height)
            drawing.scale(scale, scale)
            drawing.width *= scale
            drawing.height *= scale
            return drawing
    image_bytes = _load_image(url)
    if image_bytes:
        reader = ImageReader(BytesIO(image_bytes))
        width, height = reader.getSize()
        max_width, max_height = 55 * mm, 78 * mm
        scale = min(max_width / width, max_height / height)
        return Image(BytesIO(image_bytes), width=width * scale, height=height * scale)
    return _generic_category_image(product_label, styles, language)


def _generic_category_image(product_label: str, styles: dict[str, ParagraphStyle], language: str = "fr") -> Any:
    label = html.escape(product_label[:34], quote=True)
    generic_label = "Visuel générique" if language == "fr" else "Generic visual"
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="720" height="520"><rect width="720" height="520" fill="#f9fbff"/><rect x="80" y="70" width="560" height="380" rx="22" fill="#dbf2ed" stroke="#164698" stroke-width="3"/><rect x="210" y="135" width="300" height="210" rx="28" fill="#f9fbff" stroke="#030927" stroke-width="8"/><circle cx="286" cy="216" r="36" fill="#30ab90"/><path d="M342 260h96M342 218h96" stroke="#258090" stroke-width="18" stroke-linecap="round"/><text x="360" y="395" text-anchor="middle" font-family="Arial" font-size="26" fill="#1d2430">{label}</text><text x="360" y="430" text-anchor="middle" font-family="Arial" font-size="20" fill="#5e6875">{generic_label}</text></svg>'
    try:
        drawing = svg2rlg(BytesIO(svg.encode("utf-8")))
        if drawing and drawing.width and drawing.height:
            scale = min((55 * mm) / drawing.width, (78 * mm) / drawing.height)
            drawing.scale(scale, scale)
            drawing.width *= scale
            drawing.height *= scale
            return drawing
    except (OSError, ValueError, TypeError):
        pass
    return Table([[_p(generic_label, styles["center"])]], colWidths=[55 * mm], rowHeights=[45 * mm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE_BLUE), ("BOX", (0, 0), (-1, -1), 0.6, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))


def _verified_product_image_url(report: PrototypeAnalyzeResponse) -> str | None:
    url = report.product_image_url
    if url and url.startswith("data:image/"):
        return url
    source = next((item for item in report.sources if item.url == report.product_image_source_url), None)
    if not url:
        return None
    if not source:
        return url
    product = _product_comparison_text(report).lower().replace("-", "")
    evidence = f"{source.title} {source.url} {source.data_used}".lower().replace("-", "")
    viscosities = re.findall(r"\b\d+w\d+\b", product)
    if viscosities and not all(viscosity in evidence for viscosity in viscosities):
        return None
    if any(term in product for term in ("huile", "oil", "moteur", "engine")) and not any(term in evidence for term in ("huile", "oil", "moteur", "engine")):
        return None
    return url


def _load_image(url: str | None) -> bytes | None:
    if not url:
        return None
    try:
        raw = _read_image_source(url)
        if not raw:
            return None
        with PillowImage.open(BytesIO(raw)) as image:
            image.load()
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA")
            if not _contains_visible_image_content(image):
                return None
            output = BytesIO()
            image.save(output, format="PNG")
            return output.getvalue()
    except (OSError, ValueError, httpx.HTTPError):
        return None


def _contains_visible_image_content(image: PillowImage.Image) -> bool:
    """Reject blank/transparent remote assets instead of rendering an empty image box."""
    preview = image.convert("RGBA")
    preview.thumbnail((96, 96))
    pixels = list(preview.getdata())
    visible = sum(
        1
        for red, green, blue, alpha in pixels
        if alpha > 12 and min(red, green, blue) < 245
    )
    return visible >= max(3, len(pixels) // 200)


def _is_svg(raw: bytes) -> bool:
    return raw.lstrip().lower().startswith(b"<svg") or b"<svg" in raw[:512].lower()


def _read_image_source(url: str) -> bytes | None:
    if url.startswith("data:"):
        header, encoded = url.split(",", 1)
        return b64decode(encoded) if ";base64" in header else unquote(encoded).encode()
    response = httpx.get(
        url,
        timeout=8,
        follow_redirects=True,
        headers={"User-Agent": "NEXORA-PDF/1.0"},
    )
    response.raise_for_status()
    return response.content


def _draw_page(canvas, document) -> None:
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(document.leftMargin, 10 * mm, A4[0] - document.rightMargin, 10 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(document.leftMargin, 6 * mm, "NEXORA")
    canvas.drawRightString(A4[0] - document.rightMargin, 6 * mm, f"{document.page}")
    canvas.restoreState()


def _source_link(url: str, label: str, styles: dict[str, ParagraphStyle], language: str) -> Paragraph:
    if not url:
        return _p(_labels(language)["unavailable"], styles["table_cell"])
    return Paragraph(f'<link href="{html.escape(url, quote=True)}" color="#164698"><u>{_escape(label)}</u><br/>{_escape(_labels(language)["view_source"])}</link>', styles["table_cell"])


def _source_display_name(source: Any, fallback: str) -> str:
    title = (source.title or "").strip()
    if title.lower().startswith(("http://", "https://")):
        hostname = urlsplit(title).netloc or urlsplit(source.url or "").netloc
        return hostname.removeprefix("www.") or fallback
    return title or urlsplit(source.url or "").netloc.removeprefix("www.") or fallback


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(str(text), style)


def _value(model: Any, key: str) -> Any:
    return getattr(model, key, None) if model is not None else None


def _product_name(report: PrototypeAnalyzeResponse) -> str:
    product = report.product_understanding
    return _value(product, "original_product") or _value(product, "normalized_product") or report.product_description or "Produit"


def _product_description_for_pdf(report: PrototypeAnalyzeResponse, language: str) -> str:
    description = _localized(report.localized_analysis, "product_description", language) or report.product_description
    retail_range = _retained_retail_range(report)
    if not retail_range:
        return description
    description = _replace_retail_ranges(description, retail_range)
    if retail_range not in description:
        sentence = (
            f"Fourchette des prix retail retenus en Tunisie : {retail_range}."
            if language == "fr"
            else f"Retained Tunisia retail price range: {retail_range}."
        )
        description = f"{description} {sentence}".strip()
    return description


def _retained_retail_range(report: PrototypeAnalyzeResponse) -> str:
    prices: list[float] = []
    for offer in report.retail_offers:
        if offer.price_tnd is not None:
            prices.append(offer.price_tnd)
            continue
        prices.extend(_price_values(offer.price_range_tnd))
    if not prices:
        return ""
    return _tnd_range(min(prices), max(prices))


def _price_values(value: str | None) -> list[float]:
    if not value:
        return []
    return [float(token.replace(",", ".")) for token in re.findall(r"\d+(?:[.,]\d+)?", value)]


def _replace_retail_ranges(description: str, retail_range: str) -> str:
    return re.sub(
        r"(?<!\d)\d+(?:[.,]\d+)?\s*(?:[-–—]|à|to|and|et)\s*\d+(?:[.,]\d+)?\s*TND",
        retail_range,
        description,
        flags=re.IGNORECASE,
    )


def _localized(model: Any, key: str, language: str) -> str:
    suffix = "fr" if language == "fr" else "en"
    return _value(model, f"{key}_{suffix}") or ""


def _tnd(value: float | None, labels: dict[str, str]) -> str:
    return labels["unavailable"] if value is None else f"{value:g} TND"


def _tnd_range(minimum: float | None, maximum: float | None, unavailable: str = "Non disponible") -> str:
    if minimum is None:
        return unavailable
    if maximum is None or maximum == minimum:
        return f"{minimum:g} TND"
    return f"{minimum:g}–{maximum:g} TND"


def _price_range(minimum: float | None, maximum: float | None, currency: str, unavailable: str = "Non disponible") -> str:
    if minimum is None:
        return unavailable
    if maximum is None or maximum == minimum:
        return f"{minimum:g} {currency}"
    return f"{minimum:g}–{maximum:g} {currency}"


def _budget(profit: Any, unavailable: str = "Non disponible") -> str:
    minimum = _value(profit, "digital_ad_budget_min_tnd")
    maximum = _value(profit, "digital_ad_budget_max_tnd")
    if minimum is None:
        return unavailable
    return f"{minimum:g}–{maximum:g} TND" if maximum is not None else f"{minimum:g} TND"


def _confidence(value: str, language: str) -> str:
    values = {
        "fr": {"high": "Haute", "medium": "Moyenne", "low": "Faible", "unknown": "Inconnue"},
        "en": {"high": "High", "medium": "Medium", "low": "Low", "unknown": "Unknown"},
    }
    return values[language].get(value, values[language]["unknown"])


def _confidence_note(value: str, language: str) -> str:
    return f"{_labels(language)['confidence']}: {_confidence(value, language)}"


def _provenance(value: str, language: str) -> str:
    values = {
        "observed": "Donnée réelle" if language == "fr" else "Observed",
        "computed": "Calcul" if language == "fr" else "Computed",
        "estimate": "Estimation" if language == "fr" else "Estimate",
        "unavailable": "Non disponible" if language == "fr" else "Not available",
    }
    return values.get(value, values["unavailable"])


def _level(value: str, language: str) -> str:
    values = {"low": "Faible", "medium": "Moyenne", "high": "Forte", "unknown": "Inconnue"} if language == "fr" else {"low": "Low", "medium": "Medium", "high": "High", "unknown": "Unknown"}
    return values.get(value, values["unknown"])


def _decision(value: str, language: str) -> str:
    values = {"go": "GO", "no_go": "NO GO", "investigate_more": "À INVESTIGUER"} if language == "fr" else {"go": "GO", "no_go": "NO GO", "investigate_more": "INVESTIGATE"}
    return values.get(value, values["investigate_more"])


def _criterion_label(key: str, language: str) -> str:
    labels = {
        "market_demand": ("Demande marché", "Market demand"), "margin": ("Marge", "Margin"),
        "sourcing": ("Sourcing", "Sourcing"), "competition": ("Concurrence", "Competition"),
        "ads_potential": ("Potentiel Ads", "Ads potential"), "recurrence": ("Récurrence", "Recurrence"),
        "differentiation": ("Différenciation", "Differentiation"), "risk": ("Maîtrise du risque", "Risk management"),
    }
    return labels.get(key, (key, key))[0 if language == "fr" else 1]


def _labels(language: str) -> dict[str, str]:
    if language == "fr":
        return {
            "report_title": "Rapport d’opportunité produit", "product": "Produit", "market": "Marché", "date": "Date",
            "decision": "Décision", "score": "Score", "confidence": "Confiance", "summary": "Résumé exécutif",
            "summary_unavailable": "Résumé indisponible.", "product_image": "Image du produit", "image_unavailable": "Image produit non disponible",
            "product_section": "Produit analysé", "requested_product": "Produit demandé", "normalized_product": "Produit normalisé",
            "category": "Catégorie", "variant": "Variante / modèle", "specifications": "Format / caractéristiques",
            "sourcing_country": "Pays de sourcing", "international_sourcing": "Sourcing international", "suppliers": "Fournisseurs",
            "supplier": "Fournisseur", "product": "Produit", "price": "Prix", "tnd_conversion": "Conversion TND", "price_unit": "Unité du prix", "moq": "MOQ",
            "source": "Source", "wholesale_prices": "Prix gros", "no_wholesale": "Aucun prix de gros public fiable trouvé.",
            "landed_cost_section": "Coût rendu en Tunisie", "landed_cost": "Coût rendu estimé", "partial_estimate": "Estimation partielle — certaines charges d’importation ne sont pas incluses.",
            "component": "Composant", "supplier_price": "Prix fournisseur", "shipping": "Transport estimé", "customs": "Droits / taxes d’import", "handling": "Manutention", "misc": "Autres charges", "value": "Valeur", "data_quality": "Qualité de la donnée", "market_section": "Marché tunisien",
            "retail_prices": "Prix détail", "wholesale_observed": "Des offres grossistes tunisiennes ont été observées.", "seller": "Vendeur", "brand": "Marque", "volume": "Volume", "normalized": "Prix normalisé", "city": "Ville",
            "competition_section": "Analyse concurrentielle", "competition_level": "Niveau de concurrence", "brands": "Marques", "sellers": "Vendeurs",
            "profitability_section": "Analyse de rentabilité", "metric": "Indicateur", "quantity": "Quantité analysée", "purchase_price": "Prix d’achat unitaire",
            "selling_price": "Prix de vente recommandé", "gross_margin": "Marge brute / unité", "margin_percent": "Marge %", "gross_profit": "Profit brut",
            "ad_budget": "Budget publicitaire hypothétique", "profit_after_ads": "Profit après Ads", "commercial_section": "Potentiel commercial", "ads_section": "Potentiel Ads / marketing",
            "ads_qualitative": "Analyse qualitative : aucune valeur CPC, CPA, ROAS ou volume de recherche n’est inventée.", "risks_section": "Risques principaux",
            "decision_section": "Décision GO / NO GO", "scoring": "Scoring détaillé", "criterion": "Critère", "justification": "Justification",
            "comparability_section": "Comparabilité marché", "market_comparability": "Comparabilité marché", "comparability_unavailable": "Comparabilité non disponible.", "market_reference": "Référence marché comparable", "market_reference_unavailable": "Référence marché comparable non disponible.", "sources_section": "Sources & preuves", "sources_intro": "Les données importantes proviennent des sources ci-dessous ou de calculs explicitement indiqués.",
            "data_used": "Donnée utilisée", "view_source": "Voir la source", "unavailable": "Non disponible",
        }
    return {
        "comparability_section": "Market comparability", "market_comparability": "Market comparability", "comparability_unavailable": "Comparability unavailable.", "market_reference": "Comparable market reference", "market_reference_unavailable": "Comparable market reference unavailable.", "report_title": "Product opportunity report", "product": "Product", "market": "Market", "date": "Date", "decision": "Decision", "score": "Score", "confidence": "Confidence", "summary": "Executive summary", "summary_unavailable": "Summary unavailable.", "product_image": "Product image", "image_unavailable": "Product image unavailable", "product_section": "Product analyzed", "requested_product": "Requested product", "normalized_product": "Normalized product", "category": "Category", "variant": "Variant / model", "specifications": "Format / specifications", "sourcing_country": "Sourcing country", "international_sourcing": "International sourcing", "suppliers": "Suppliers", "supplier": "Supplier", "product": "Product", "price": "Price", "tnd_conversion": "TND conversion", "moq": "MOQ", "source": "Source", "wholesale_prices": "Wholesale prices", "wholesale_observed": "Tunisian wholesale offers were observed.", "no_wholesale": "No reliable public wholesale price found.", "landed_cost_section": "Landed cost in Tunisia", "landed_cost": "Estimated landed cost", "partial_estimate": "Partial estimate — some import charges are not included.", "component": "Component", "supplier_price": "Supplier price", "shipping": "Estimated shipping", "customs": "Import duties / taxes", "handling": "Handling", "misc": "Other charges", "value": "Value", "data_quality": "Data quality", "market_section": "Tunisia market", "retail_prices": "Retail prices", "seller": "Seller", "brand": "Brand", "volume": "Volume", "normalized": "Normalized price", "city": "City", "competition_section": "Competitive analysis", "competition_level": "Competition level", "brands": "Brands", "sellers": "Sellers", "profitability_section": "Profitability analysis", "metric": "Metric", "quantity": "Analyzed quantity", "purchase_price": "Unit purchase price", "selling_price": "Recommended selling price", "gross_margin": "Gross margin / unit", "margin_percent": "Margin %", "gross_profit": "Gross profit", "ad_budget": "Hypothetical ad budget", "profit_after_ads": "Profit after Ads", "commercial_section": "Commercial potential", "ads_section": "Ads / marketing potential", "ads_qualitative": "Qualitative analysis: no CPC, CPA, ROAS or search-volume values are invented.", "risks_section": "Main risks", "decision_section": "GO / NO GO decision", "scoring": "Detailed scoring", "criterion": "Criterion", "justification": "Justification", "sources_section": "Sources & evidence", "sources_intro": "Key data comes from the sources below or from explicitly labeled calculations.", "data_used": "Data used", "view_source": "View source", "unavailable": "Not available",
    }


def _escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _filename_slug(value: str) -> str:
    value = value.replace("-", "")
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return value[:80]
