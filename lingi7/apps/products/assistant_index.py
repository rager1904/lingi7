"""
Assistant catalog indexing bridge.

Exports visible Django products into the assistant catalog CSV and pushes them
to the catalog retriever service when available.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

import requests
from django.conf import settings

from apps.products.models import Product

logger = logging.getLogger(__name__)

ASSISTANT_CATALOG_COLUMNS = [
    "pk",
    "category",
    "subcategory",
    "name",
    "description",
    "url",
    "price",
    "image",
]


class AssistantCatalogIndexer:
    """Keeps assistant retrieval aligned with approved marketplace products."""

    @classmethod
    def index_product(cls, product: Product) -> bool:
        if not getattr(settings, "ASSISTANT_CATALOG_INDEXING_ENABLED", True):
            return False

        product = (
            Product.objects.select_related("category", "store")
            .prefetch_related("images")
            .get(pk=product.pk)
        )
        if not product.is_visible:
            logger.info("Assistant indexing skipped for non-visible product=%s", product.pk)
            return False

        row = cls._product_to_row(product)
        cls._upsert_csv_row(row)
        cls._push_to_retriever(row)
        logger.info("Assistant catalog indexed product=%s", product.pk)
        return True

    @staticmethod
    def _product_to_row(product: Product) -> dict[str, str]:
        category = product.category.name if product.category_id else "marketplace"
        tags = product.suggested_tags or []
        subcategory = str(tags[0]) if tags else category
        description = (
            (product.descriptions_i18n or {}).get("en")
            or product.meta_description
            or product.description
        )
        image = ""
        primary = product.images.order_by("position").first()
        if primary and primary.image:
            try:
                image = primary.image.url
            except ValueError:
                image = ""

        return {
            "pk": str(product.pk),
            "category": category,
            "subcategory": subcategory,
            "name": product.ai_enhanced_title or product.name,
            "description": description,
            "url": f"/products/{product.slug}",
            "price": str(product.price),
            "image": image,
        }

    @classmethod
    def _upsert_csv_row(cls, row: dict[str, str]) -> None:
        csv_path = Path(settings.ASSISTANT_CATALOG_CSV_PATH)
        csv_path.parent.mkdir(parents=True, exist_ok=True)

        rows: list[dict[str, str]] = []
        if csv_path.exists():
            with csv_path.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                for existing in reader:
                    existing_pk = str(existing.get("pk") or "")
                    if existing_pk and existing_pk == row["pk"]:
                        continue
                    rows.append({col: str(existing.get(col, "")) for col in ASSISTANT_CATALOG_COLUMNS})

        rows.append(row)
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=ASSISTANT_CATALOG_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _push_to_retriever(row: dict[str, str]) -> None:
        base_url = str(getattr(settings, "CATALOG_RETRIEVER_URL", "")).rstrip("/")
        if not base_url:
            return
        try:
            response = requests.post(
                f"{base_url}/index/products",
                json={"products": [row]},
                timeout=getattr(settings, "CATALOG_RETRIEVER_TIMEOUT", 20),
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning(
                "Assistant live index push failed; CSV export remains available. product=%s error=%s",
                row.get("pk"),
                exc,
            )
