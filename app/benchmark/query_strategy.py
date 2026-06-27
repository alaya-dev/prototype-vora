from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class RegionalQueries:
    tunisia: list[str]
    china: list[str]

    @property
    def total_count(self) -> int:
        return len(self.tunisia) + len(self.china)


@dataclass(frozen=True)
class ProductIntent:
    original_product: str
    normalized_product: str
    product_category: str
    brand_or_model: str | None
    must_include_terms: list[str]
    optional_terms: list[str]
    excluded_terms: list[str]
    china_search_name: str
    tunisia_search_name: str


def build_regional_queries(product: str, max_queries_per_region: int) -> RegionalQueries:
    limit = max(1, max_queries_per_region)
    intent = infer_product_intent(product)
    tunisia_templates = [
        "{product} prix Tunisie",
        "{product} achat Tunisie",
        "{product} boutique Tunisie",
        "{product} vente Tunisie",
        "{product} site:.tn",
        "{product} site:.com.tn",
        "{product} prix site:.tn",
        "{product} achat site:.tn",
        "{product} boutique site:.tn",
        "{product} vente site:.tn",
    ]
    china_templates = [
        "{product} wholesale unit price China",
        "{product} factory wholesale price",
        "{product} bulk price MOQ",
        "{product} OEM ODM wholesale price",
        "{product} Alibaba wholesale price MOQ",
        "{product} Made-in-China wholesale price MOQ",
        "{product} Global Sources wholesale price MOQ",
        "{product} China supplier product price MOQ",
        "{product} manufacturer wholesale unit price",
    ]
    return RegionalQueries(
        tunisia=[
            template.format(product=intent.tunisia_search_name)
            for template in tunisia_templates[:limit]
        ],
        china=[
            template.format(product=intent.china_search_name)
            for template in china_templates[:limit]
        ],
    )


def infer_product_intent(product: str) -> ProductIntent:
    original = product.strip()
    normalized = re.sub(r"\s+", " ", original)
    lowered = normalized.lower()

    if "vintage t9" in lowered or re.search(r"\bt9\b", lowered):
        return ProductIntent(
            original_product=original,
            normalized_product="T9 vintage hair trimmer",
            product_category="hair trimmer",
            brand_or_model="T9",
            must_include_terms=["T9", "trimmer"],
            optional_terms=["vintage", "hair", "clipper"],
            excluded_terms=["toy", "decoration"],
            china_search_name="T9 vintage hair trimmer",
            tunisia_search_name="T9 vintage hair trimmer",
        )

    if "hoco" in lowered and "earbud" in lowered:
        return ProductIntent(
            original_product=original,
            normalized_product="HOCO wireless earbuds",
            product_category="wireless earbuds",
            brand_or_model="HOCO",
            must_include_terms=["HOCO", "wireless", "earbuds"],
            optional_terms=["bluetooth", "tws"],
            excluded_terms=["wired", "headphones"],
            china_search_name="HOCO wireless earbuds",
            tunisia_search_name="HOCO wireless earbuds",
        )

    if "portable blender" in lowered or "mini blender" in lowered:
        return ProductIntent(
            original_product=original,
            normalized_product="mini portable blender",
            product_category="portable blender",
            brand_or_model=None,
            must_include_terms=["portable", "blender"],
            optional_terms=["mini", "usb", "personal"],
            excluded_terms=["industrial", "commercial"],
            china_search_name="mini portable blender",
            tunisia_search_name="mini portable blender",
        )

    if "led strip" in lowered:
        return ProductIntent(
            original_product=original,
            normalized_product="LED strip lights",
            product_category="LED strip lights",
            brand_or_model=None,
            must_include_terms=["LED", "strip"],
            optional_terms=["lights", "rgb"],
            excluded_terms=["bulb", "lamp"],
            china_search_name="LED strip lights",
            tunisia_search_name="LED strip lights",
        )

    return ProductIntent(
        original_product=original,
        normalized_product=normalized,
        product_category="",
        brand_or_model=None,
        must_include_terms=[term for term in normalized.split() if term],
        optional_terms=[],
        excluded_terms=[],
        china_search_name=normalized,
        tunisia_search_name=normalized,
    )
