from __future__ import annotations

from base64 import b64decode
from datetime import date
from io import BytesIO
import html
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote

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
    decision = _decision(report.recommendation, language)
    confidence = _confidence(report.decision_scores.confidence, language)
    metadata = [
        [_p(labels["product"], styles["kpi_label"]), _p(product, styles["kpi_value"])],
        [_p(labels["market"], styles["kpi_label"]), _p(report.target_market, styles["kpi_value"])],
        [_p(labels["date"], styles["kpi_label"]), _p(date.today().isoformat(), styles["kpi_value"])],
        [_p(labels["decision"], styles["kpi_label"]), _p(decision, styles["kpi_value"])],
        [_p(labels["score"], styles["kpi_label"]), _p(f"{report.detailed_scoring.total}/100", styles["kpi_value"])],
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
    product_image = _product_image(report.product_image_url, styles, language)
    summary = _localized(report.localized_analysis, "business_reading", language)
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
        (labels["category"], _value(product, "product_category") or labels["unavailable"]),
        (labels["variant"], _value(product, "brand_or_model") or labels["unavailable"]),
        (labels["specifications"], ", ".join(_value(product, "technical_specs") or []) or labels["unavailable"]),
        (labels["market"], report.target_market),
        (labels["sourcing_country"], report.sourcing_country),
    ]
    description = _localized(report.localized_analysis, "product_description", language) or report.product_description
    return _section(labels["product_section"], [_p(_escape(description), styles["body"])], _key_value_table(rows, styles), styles)


def _sourcing_section(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    labels = _labels(language)
    china_rows = [
        [offer.name or labels["unavailable"], offer.product_title or labels["unavailable"],
         _price_range(offer.price_min, offer.price_max, offer.currency or "USD"),
         _tnd_range(offer.price_min_tnd, offer.price_max_tnd), offer.moq or labels["unavailable"],
         _source_link(offer.source_url, offer.name or labels["source"], styles, language)]
        for offer in report.china_offers
    ]
    wholesale_rows = [
        [offer.name or labels["unavailable"], offer.product_title or labels["unavailable"],
         _tnd_range(offer.price_min_tnd, offer.price_max_tnd),
         _source_link(offer.source_url, offer.name or labels["source"], styles, language)]
        for offer in report.tunisia_wholesale_offers
    ]
    blocks: list[Any] = []
    blocks.append(_p(labels["international_sourcing"], styles["section"]))
    blocks.append(_p(_confidence_note(report.sourcing_summary.evidence_confidence, language), styles["muted"]))
    blocks.append(_p(labels["suppliers"], styles["subsection"]))
    blocks.append(_table(
        [labels["supplier"], labels["product"], labels["price"], labels["tnd_conversion"], labels["moq"], labels["source"]],
        china_rows or [[labels["unavailable"]] * 6], [30, 42, 24, 27, 22, 28], styles,
    ))
    blocks.append(_p(labels["wholesale_prices"], styles["subsection"]))
    if wholesale_rows:
        blocks.append(_table([labels["supplier"], labels["product"], labels["price"], labels["source"]], wholesale_rows, [42, 65, 30, 28], styles))
    else:
        blocks.append(_p(labels["no_wholesale"], styles["body"]))
    return blocks


def _landed_cost_section(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    labels = _labels(language)
    rows = [
        [labels.get(component.label_key, component.label_key), _tnd(component.value_tnd, labels), _provenance(component.provenance, language)]
        for component in report.landed_cost.components
    ]
    rows.append([labels["landed_cost"], _tnd(report.landed_cost.total_tnd, labels), _provenance("estimate", language)])
    return _section(labels["landed_cost_section"], [_p(_escape(_landed_cost_note(report, language)), styles["muted"])], _table(
        [labels["component"], labels["value"], labels["data_quality"]], rows, [70, 45, 45], styles,
    ), styles)


def _market_section(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    labels = _labels(language)
    retail_rows = [
        [offer.seller_name or labels["unavailable"], offer.brand or labels["unavailable"], offer.product_title or labels["unavailable"],
         offer.volume_text or labels["unavailable"], _tnd_range(offer.price_tnd, offer.price_tnd) if offer.price_tnd is not None else offer.price_range_tnd or labels["unavailable"],
         _normalized_retail_price(offer, language, labels), offer.city or labels["unavailable"],
         _source_link(offer.source_url, offer.seller_name or labels["source"], styles, language)]
        for offer in report.retail_offers
    ]
    blocks = [_p(labels["market_section"], styles["section"]), _p(labels["retail_prices"], styles["subsection"])]
    blocks.append(_table(
        [labels["seller"], labels["brand"], labels["product"], labels["volume"], labels["price"], labels["normalized"], labels["city"], labels["source"]],
        retail_rows or [[labels["unavailable"]] * 8], [27, 22, 42, 18, 23, 35, 22, 26], styles,
    ))
    blocks.append(_p(labels["wholesale_prices"], styles["subsection"]))
    blocks.append(_p(_escape(labels["wholesale_observed"] if report.tunisia_wholesale_offers else labels["no_wholesale"]), styles["body"]))
    return blocks


def _competition_section(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    labels = _labels(language)
    brands = ", ".join(sorted({offer.brand for offer in report.retail_offers if offer.brand})) or labels["unavailable"]
    sellers = ", ".join(sorted({offer.seller_name for offer in report.retail_offers if offer.seller_name})) or labels["unavailable"]
    body = f"{labels['competition_level']}: {_level(report.competition_level, language)}. {labels['brands']}: {brands}. {labels['sellers']}: {sellers}."
    return _section(labels["competition_section"], [_p(_escape(body), styles["body"])], None, styles)


def _profitability_section(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    labels = _labels(language)
    profit = report.profitability_estimate
    rows = [
        [labels["quantity"], str(report.analysis_quantity_units)],
        [labels["purchase_price"], _tnd(profit.source_unit_price_tnd, labels)],
        [labels["landed_cost"], _tnd(profit.estimated_landed_cost_per_unit_tnd, labels)],
        [labels["selling_price"], _tnd(profit.estimated_selling_price_tnd, labels)],
        [labels["gross_margin"], _tnd(profit.gross_margin_per_unit_before_marketing_tnd, labels)],
        [labels["margin_percent"], _margin_percent(profit)],
        [labels["gross_profit"], _tnd(profit.gross_profit_for_1000_before_marketing_tnd, labels)],
        [labels["ad_budget"], _budget(profit)],
        [labels["profit_after_ads"], _tnd(profit.net_profit_for_1000_after_marketing_tnd, labels)],
    ]
    notes = _profitability_notes(profit, language)
    flowables = [_p(labels["profitability_section"], styles["section"]), _table([labels["metric"], labels["value"]], rows, [85, 90], styles)]
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
    risks = list(dict.fromkeys([*report.profitability_estimate.risks, *report.warnings]))
    content = [_p(f"• {_escape(risk)}", styles["body"]) for risk in _pdf_risks(report, language)] or [_p(labels["unavailable"], styles["body"])]
    return _section(labels["risks_section"], content, None, styles)


def _decision_section(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    labels = _labels(language)
    scores = [[_criterion_label(item.key, language), f"{item.score}/{item.max_score}", _criterion_justification(item, language)] for item in report.detailed_scoring.criteria]
    blocks = [_p(labels["decision_section"], styles["section"]), _p(_decision(report.recommendation, language), styles["decision"]), _p(
        f"{labels['score']}: {report.detailed_scoring.total}/100 · {labels['confidence']}: {_confidence(report.decision_scores.confidence, language)}", styles["center"],
    )]
    decision_reason = _decision_reason(report, language)
    if decision_reason:
        blocks.append(_p(_escape(decision_reason), styles["body"]))
    blocks.append(_p(labels["scoring"], styles["subsection"]))
    blocks.append(_table([labels["criterion"], labels["score"], labels["justification"]], scores or [[labels["unavailable"]] * 3], [38, 25, 112], styles))
    return blocks


def _sources_section(report: PrototypeAnalyzeResponse, language: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    labels = _labels(language)
    rows = [[_source_link(source.url, source.title or labels["source"], styles, language), _source_data_used(source.data_used, language), _confidence(source.confidence, language)] for source in report.sources]
    return _section(labels["sources_section"], [_p(labels["sources_intro"], styles["muted"])], _table(
        [labels["source"], labels["data_used"], labels["confidence"]], rows or [[labels["unavailable"]] * 3], [80, 70, 25], styles,
    ), styles)


def _section(title: str, intro: list[Any], table: Any, styles: dict[str, ParagraphStyle]) -> list[Any]:
    flowables: list[Any] = [KeepTogether([_p(title, styles["section"]), *intro])]
    if table is not None:
        flowables.append(table)
    return flowables


def _landed_cost_note(report: PrototypeAnalyzeResponse, language: str) -> str:
    if language != "fr":
        return report.landed_cost.note or _labels(language)["partial_estimate"]
    components = {component.label_key: component.value_tnd for component in report.landed_cost.components}
    parts = [
        f"Prix fournisseur {_tnd(components.get('supplier_price'), _labels(language))}",
        f"transport {_tnd(components.get('shipping'), _labels(language))}",
        f"droits et taxes {_tnd(components.get('customs'), _labels(language))}",
        f"manutention {_tnd(components.get('handling'), _labels(language))}",
        f"autres charges {_tnd(components.get('misc'), _labels(language))}",
    ]
    return " + ".join(parts) + f" = coût rendu estimé {_tnd(report.landed_cost.total_tnd, _labels(language))}. " + _labels(language)["partial_estimate"]


def _profitability_notes(profit: Any, language: str) -> list[str]:
    if language != "fr":
        return [profit.pricing_basis, *profit.assumptions]
    basis = profit.pricing_basis
    if "normalized" in basis.lower():
        basis = "Les prix ont été normalisés par litre ou par kilogramme car les conditionnements diffèrent."
    elif basis:
        basis = "Les prix des conditionnements comparables ont été utilisés sans conversion supplémentaire."
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
    if report.comparability.level in {"low", "unknown"}:
        risks.append("La comparabilité des produits doit être confirmée avant d’utiliser la marge comme argument principal.")
    if report.profitability_estimate.risks:
        risks.append("La qualité, la conformité et les conditions fournisseur doivent être vérifiées avant investissement.")
    return list(dict.fromkeys(risks))


def _decision_reason(report: PrototypeAnalyzeResponse, language: str) -> str:
    localized = _localized(report.localized_analysis, "business_reading", language)
    if localized:
        return localized
    if language != "fr":
        return report.recommendation_reason
    return {
        "go": "Les éléments disponibles justifient une vérification fournisseur et un test d’échantillon.",
        "no_go": "La marge ou la qualité des preuves ne justifie pas un investissement immédiat.",
        "investigate_more": "Le produit présente un potentiel, mais des vérifications fournisseur, marché et logistique restent nécessaires.",
    }.get(report.recommendation, "Des vérifications complémentaires sont nécessaires.")


def _criterion_justification(item: Any, language: str) -> str:
    if language != "fr":
        return item.justification or "Not available"
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


def _normalized_retail_price(offer: Any, language: str, labels: dict[str, str]) -> str:
    if offer.normalized_price_per_unit_tnd is not None:
        unit = "unité" if language == "fr" else "unit"
        return f"{offer.normalized_price_per_unit_tnd:g} TND/{unit}"
    if not offer.normalized_price_text:
        return labels["unavailable"]
    if language == "fr":
        return "Prix normalisé disponible"
    return offer.normalized_price_text


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


def _product_image(url: str | None, styles: dict[str, ParagraphStyle], language: str) -> Any:
    image_bytes = _load_image(url)
    if image_bytes:
        reader = ImageReader(BytesIO(image_bytes))
        width, height = reader.getSize()
        max_width, max_height = 55 * mm, 78 * mm
        scale = min(max_width / width, max_height / height)
        return Image(BytesIO(image_bytes), width=width * scale, height=height * scale)
    return Table([[_p(_labels(language)["image_unavailable"], styles["center"])]], colWidths=[55 * mm], rowHeights=[45 * mm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE_BLUE),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))


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
            output = BytesIO()
            image.save(output, format="PNG")
            return output.getvalue()
    except (OSError, ValueError, httpx.HTTPError):
        return None


def _read_image_source(url: str) -> bytes | None:
    if url.startswith("data:"):
        header, encoded = url.split(",", 1)
        return b64decode(encoded) if ";base64" in header else unquote(encoded).encode()
    response = httpx.get(url, timeout=8, follow_redirects=True)
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


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(str(text), style)


def _value(model: Any, key: str) -> Any:
    return getattr(model, key, None) if model is not None else None


def _product_name(report: PrototypeAnalyzeResponse) -> str:
    product = report.product_understanding
    return _value(product, "original_product") or _value(product, "normalized_product") or report.product_description or "Produit"


def _localized(model: Any, key: str, language: str) -> str:
    suffix = "fr" if language == "fr" else "en"
    return _value(model, f"{key}_{suffix}") or ""


def _tnd(value: float | None, labels: dict[str, str]) -> str:
    return labels["unavailable"] if value is None else f"{value:g} TND"


def _tnd_range(minimum: float | None, maximum: float | None) -> str:
    if minimum is None:
        return "Non disponible"
    if maximum is None or maximum == minimum:
        return f"{minimum:g} TND"
    return f"{minimum:g}–{maximum:g} TND"


def _price_range(minimum: float | None, maximum: float | None, currency: str) -> str:
    if minimum is None:
        return "Non disponible"
    if maximum is None or maximum == minimum:
        return f"{minimum:g} {currency}"
    return f"{minimum:g}–{maximum:g} {currency}"


def _margin_percent(profit: Any) -> str:
    margin = _value(profit, "gross_margin_per_unit_before_marketing_tnd")
    selling = _value(profit, "estimated_selling_price_tnd")
    if margin is None or not selling:
        return "Non disponible"
    return f"{margin / selling * 100:.1f}%"


def _budget(profit: Any) -> str:
    minimum = _value(profit, "digital_ad_budget_min_tnd")
    maximum = _value(profit, "digital_ad_budget_max_tnd")
    if minimum is None:
        return "Non disponible"
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
        "differentiation": ("Différenciation", "Differentiation"), "risk": ("Risque", "Risk"),
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
            "supplier": "Fournisseur", "product": "Produit", "price": "Prix", "tnd_conversion": "Conversion TND", "moq": "MOQ",
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
            "sources_section": "Sources & preuves", "sources_intro": "Les données importantes proviennent des sources ci-dessous ou de calculs explicitement indiqués.",
            "data_used": "Donnée utilisée", "view_source": "Voir la source", "unavailable": "Non disponible",
        }
    return {
        "report_title": "Product opportunity report", "product": "Product", "market": "Market", "date": "Date", "decision": "Decision", "score": "Score", "confidence": "Confidence", "summary": "Executive summary", "summary_unavailable": "Summary unavailable.", "product_image": "Product image", "image_unavailable": "Product image unavailable", "product_section": "Product analyzed", "requested_product": "Requested product", "normalized_product": "Normalized product", "category": "Category", "variant": "Variant / model", "specifications": "Format / specifications", "sourcing_country": "Sourcing country", "international_sourcing": "International sourcing", "suppliers": "Suppliers", "supplier": "Supplier", "product": "Product", "price": "Price", "tnd_conversion": "TND conversion", "moq": "MOQ", "source": "Source", "wholesale_prices": "Wholesale prices", "wholesale_observed": "Tunisian wholesale offers were observed.", "no_wholesale": "No reliable public wholesale price found.", "landed_cost_section": "Landed cost in Tunisia", "landed_cost": "Estimated landed cost", "partial_estimate": "Partial estimate — some import charges are not included.", "component": "Component", "supplier_price": "Supplier price", "shipping": "Estimated shipping", "customs": "Import duties / taxes", "handling": "Handling", "misc": "Other charges", "value": "Value", "data_quality": "Data quality", "market_section": "Tunisia market", "retail_prices": "Retail prices", "seller": "Seller", "brand": "Brand", "volume": "Volume", "normalized": "Normalized price", "city": "City", "competition_section": "Competitive analysis", "competition_level": "Competition level", "brands": "Brands", "sellers": "Sellers", "profitability_section": "Profitability analysis", "metric": "Metric", "quantity": "Analyzed quantity", "purchase_price": "Unit purchase price", "selling_price": "Recommended selling price", "gross_margin": "Gross margin / unit", "margin_percent": "Margin %", "gross_profit": "Gross profit", "ad_budget": "Hypothetical ad budget", "profit_after_ads": "Profit after Ads", "commercial_section": "Commercial potential", "ads_section": "Ads / marketing potential", "ads_qualitative": "Qualitative analysis: no CPC, CPA, ROAS or search-volume values are invented.", "risks_section": "Main risks", "decision_section": "GO / NO GO decision", "scoring": "Detailed scoring", "criterion": "Criterion", "justification": "Justification", "sources_section": "Sources & evidence", "sources_intro": "Key data comes from the sources below or from explicitly labeled calculations.", "data_used": "Data used", "view_source": "View source", "unavailable": "Not available",
    }


def _escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _filename_slug(value: str) -> str:
    value = value.replace("-", "")
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return value[:80]
