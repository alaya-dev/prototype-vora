from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegionalQueries:
    tunisia: list[str]
    china: list[str]

    @property
    def total_count(self) -> int:
        return len(self.tunisia) + len(self.china)


def build_regional_queries(product: str, max_queries_per_region: int) -> RegionalQueries:
    limit = max(1, max_queries_per_region)
    tunisia_templates = [
        "{product} prix Tunisie",
        "{product} achat Tunisie",
        "{product} boutique Tunisie",
        "{product} site:mytek.tn",
        "{product} site:jumia.com.tn",
        "{product} site:tayara.tn",
        "{product} site:spacenet.tn",
        "{product} site:shopiwell.tn",
        "{product} site:barka.tn",
    ]
    china_templates = [
        "{product} China supplier price MOQ",
        "{product} manufacturer China wholesale",
        "{product} Alibaba supplier MOQ price",
        "{product} Made-in-China supplier",
        "{product} Global Sources supplier",
        "{product} wholesale China factory",
        "{product} OEM ODM supplier",
    ]
    return RegionalQueries(
        tunisia=[template.format(product=product) for template in tunisia_templates[:limit]],
        china=[template.format(product=product) for template in china_templates[:limit]],
    )
