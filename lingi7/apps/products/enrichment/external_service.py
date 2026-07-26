"""
Client for the standalone catalog enrichment service.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests
from django.conf import settings

from apps.products.models import Product

logger = logging.getLogger(__name__)


class ExternalCatalogEnrichmentClient:
    """Calls the standalone enrichment FastAPI app through the backend."""

    def __init__(self) -> None:
        self.base_url = str(settings.CATALOG_ENRICHMENT_SERVICE_URL).rstrip("/")
        self.timeout = settings.CATALOG_ENRICHMENT_SERVICE_TIMEOUT

    def is_configured(self) -> bool:
        return bool(self.base_url)

    def analyze_product(self, product: Product) -> dict[str, Any] | None:
        primary = product.images.order_by("position").first()
        if not primary or not primary.image:
            return None

        product_data = {
            "id": product.pk,
            "title": product.name,
            "description": product.description,
            "category": product.category.name if product.category_id else "",
            "price": str(product.price),
            "condition": product.condition,
            "sku": product.sku,
        }

        try:
            primary.image.open("rb")
            try:
                files = {
                    "image": (
                        primary.image.name.rsplit("/", 1)[-1],
                        primary.image,
                        "image/jpeg",
                    )
                }
                data = {
                    "locale": "en-US",
                    "product_data": json.dumps(product_data),
                    "brand_instructions": "Optimize for Lingi7 marketplace listings in Zambia.",
                }
                response = requests.post(
                    f"{self.base_url}/vlm/analyze",
                    files=files,
                    data=data,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                payload = response.json()
            finally:
                primary.image.close()
        except (OSError, ValueError, requests.RequestException) as exc:
            logger.info(
                "Standalone enrichment unavailable for product=%s; local fallback will run. error=%s",
                product.pk,
                exc,
            )
            return None

        if not isinstance(payload, dict):
            return None
        return payload
