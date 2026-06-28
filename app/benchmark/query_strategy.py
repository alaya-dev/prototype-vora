from __future__ import annotations

from dataclasses import dataclass
import re

from app.schemas import ProductUnderstanding

@dataclass(frozen=True)
class RegionalQueries:
    china_sourcing: list[str]
    tunisia_sourcing: list[str]
    tunisia_retail: list[str]

    @property
    def total_count(self) -> int:
        return len(self.china_sourcing) + len(self.tunisia_sourcing) + len(self.tunisia_retail)

    @property
    def china(self) -> list[str]:
        return self.china_sourcing

    @property
    def tunisia(self) -> list[str]:
        return self.tunisia_retail


@dataclass(frozen=True)
class ProductIntent:
    original_product: str
    normalized_product: str
    product_category: str
    brand_or_model: str | None
    must_include_terms: list[str]
    optional_terms: list[str]
    excluded_terms: list[str]
    english_search_name: str
    french_search_name: str

    @property
    def china_search_name(self) -> str:
        return self.english_search_name

    @property
    def tunisia_search_name(self) -> str:
        return self.french_search_name


def build_regional_queries(product: str | ProductUnderstanding, max_queries_per_region: int) -> RegionalQueries:
    limit = max(1, max_queries_per_region)
    intent = infer_product_intent(product)
    china_sourcing_templates = [
        "{product} wholesale unit price China",
        "{product} factory price MOQ",
        "{product} manufacturer price MOQ",
        "{product} bulk price MOQ",
        "{product} OEM ODM wholesale price",
        "{product} Alibaba product wholesale price MOQ",
        "{product} Made-in-China product price MOQ",
        "{product} Global Sources product price MOQ",
        "{product} supplier product price MOQ",
        "{product} manufacturer wholesale unit price",
        "{product} wholesale price per piece",
    ]
    tunisia_sourcing_templates = [
        "{product} grossiste Tunisie prix",
        "{product} prix gros Tunisie",
        "{product} vente en gros Tunisie",
        "{product} fournisseur Tunisie prix gros",
        "{product} distributeur Tunisie prix",
        "{product} importateur Tunisie prix",
        "{product} fabricant Tunisie prix",
        "{product} usine Tunisie prix",
        "{product} B2B Tunisie",
        "{product} prix revendeur Tunisie",
        "{product} vente par lot Tunisie",
        "{product} semi gros Tunisie",
    ]
    tunisia_retail_templates = [
        "{product} prix Tunisie",
        "{product} achat Tunisie",
        "{product} vente Tunisie",
        "{product} boutique Tunisie",
        "{product} site:.tn",
        "{product} site:.com.tn",
        "{product} Jumia Tunisie prix",
        "{product} Tayara Tunisie prix",
        "{product} boutique en ligne Tunisie",
        "{product} magasin Tunisie",
    ]
    return RegionalQueries(
        china_sourcing=[
            template.format(product=intent.china_search_name)
            for template in china_sourcing_templates[:limit]
        ],
        tunisia_sourcing=[
            template.format(product=intent.tunisia_search_name)
            for template in tunisia_sourcing_templates[:limit]
        ],
        tunisia_retail=[
            template.format(product=intent.tunisia_search_name)
            for template in tunisia_retail_templates[:limit]
        ],
    )


def infer_product_intent(product: str | ProductUnderstanding) -> ProductIntent:
    if isinstance(product, ProductUnderstanding):
        return ProductIntent(
            original_product=product.original_product,
            normalized_product=product.normalized_product,
            product_category=product.product_category,
            brand_or_model=product.brand_or_model,
            must_include_terms=product.must_include_terms,
            optional_terms=product.optional_terms,
            excluded_terms=product.excluded_terms,
            english_search_name=product.english_search_name or product.normalized_product or product.original_product,
            french_search_name=product.french_search_name or product.normalized_product or product.original_product,
        )
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
            english_search_name="T9 vintage hair trimmer",
            french_search_name="tondeuse cheveux T9 vintage",
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
            english_search_name="HOCO wireless earbuds",
            french_search_name="écouteurs sans fil HOCO",
        )

    if "portable blender" in lowered or "mini blender" in lowered:
        return ProductIntent(
            original_product=original,
            normalized_product="portable blender",
            product_category="portable blender",
            brand_or_model=None,
            must_include_terms=["portable", "blender"],
            optional_terms=["mini", "usb", "personal"],
            excluded_terms=["industrial", "commercial"],
            english_search_name="portable blender",
            french_search_name="mixeur portable",
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
            english_search_name="LED strip lights",
            french_search_name="ruban LED",
        )

    return ProductIntent(
        original_product=original,
        normalized_product=normalized,
        product_category="",
        brand_or_model=None,
        must_include_terms=[term for term in normalized.split() if term],
        optional_terms=[],
        excluded_terms=[],
        english_search_name=normalized,
        french_search_name=normalized,
    )
