from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SupplierConfidence = Literal["high", "medium", "low"]
SupplierType = Literal[
    "marketplace",
    "local_provider",
    "seller",
    "source",
    "manufacturer",
    "trading_company",
    "marketplace_source",
    "unknown",
]
ResearchSourceType = Literal["tunisia_market", "china_supplier", "general_context"]
ProductCategory = Literal[
    "Agriculture & Food",
    "Apparel & Accessories",
    "Arts & Crafts",
    "Auto, Motorcycle Parts & Accessories",
    "Bags, Cases & Boxes",
    "Chemicals",
    "Computer Products",
    "Construction & Decoration",
    "Consumer Electronics",
    "Electrical & Electronics",
    "Furniture",
    "Health & Medicine",
    "Industrial Equipment & Components",
    "Instruments & Meters",
    "Light Industry & Daily Use",
    "Lights & Lighting",
    "Manufacturing & Processing Machinery",
    "Metallurgy, Mineral & Energy",
    "Office Supplies",
    "Packaging & Printing",
    "Security & Protection",
    "Service",
    "Sporting Goods & Recreation",
    "Textile",
    "Tools & Hardware",
    "Toys",
    "Transportation",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AnalyzeRequest(StrictModel):
    product: str = Field(default="", max_length=200)
    category: ProductCategory | None = None


class IntentResult(StrictModel):
    is_valid_product: bool
    normalized_product: str | None = None
    reason: str


class SupplierOption(StrictModel):
    name: str
    type: SupplierType
    product_title: str | None = None
    price_range_tnd: str | None = None
    price_range_usd: str | None = None
    moq: str | None = None
    source_url: str | None = None
    confidence: SupplierConfidence
    notes: str


class ResearchSource(StrictModel):
    title: str
    url: str
    source_type: ResearchSourceType


class MarketResearchResult(StrictModel):
    market_summary: str
    tunisia_suppliers: list[SupplierOption] = Field(default_factory=list)
    research_sources: list[ResearchSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ChinaSupplierResearchResult(StrictModel):
    china_suppliers: list[SupplierOption] = Field(default_factory=list)
    research_sources: list[ResearchSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ProductAnalysisResponse(StrictModel):
    product: str
    is_valid_product: bool
    intent_reason: str
    market_summary: str
    tunisia_suppliers: list[SupplierOption] = Field(default_factory=list)
    china_suppliers: list[SupplierOption] = Field(default_factory=list)
    research_sources: list[ResearchSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
