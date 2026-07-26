"""Rule-based enrichment when LLM / VLM is unavailable."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.products.models import Category, Product


def _title_case(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name.strip())
    if not cleaned:
        return name
    return cleaned[0].upper() + cleaned[1:]


def _tokenize_keywords(name: str, category_name: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9]+", f"{name} {category_name}".lower())
    seen: set[str] = set()
    keywords: list[str] = []
    for word in words:
        if len(word) < 3 or word in seen:
            continue
        seen.add(word)
        keywords.append(word)
    return keywords[:10]


def enrich_without_llm(product: Product, categories: list[Category]) -> dict[str, Any]:
    """Produce basic enrichment payload from product fields alone."""
    category_name = product.category.name if product.category_id else ""
    enhanced_title = _title_case(product.name)
    description_en = product.description.strip() or (
        f"{enhanced_title} — quality {product.get_condition_display().lower()} item "
        f"listed in {category_name or 'our marketplace'}."
    )

    meta_title = enhanced_title[:60]
    meta_description = description_en[:155]
    keywords = _tokenize_keywords(product.name, category_name)

    return {
        "enhanced_title": enhanced_title,
        "description_en": description_en,
        "description_fr": description_en,
        "description_sw": description_en,
        "features": keywords[:5],
        "specs": {"condition": product.get_condition_display()},
        "meta_title": meta_title,
        "meta_description": meta_description,
        "search_keywords": keywords,
        "tags": keywords[:6],
        "category_id": product.category_id,
        "category_confidence": 0.5,
        "llm_used": False,
    }
