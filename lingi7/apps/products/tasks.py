"""
Product Celery tasks — catalog enrichment.

Enrichment runs on the default queue alongside escrow reconciliation tasks.
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.products.enrichment.service import CatalogEnrichmentService
from apps.products.exceptions import EnrichmentError

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    name="apps.products.tasks.enrich_product_task",
)
def enrich_product_task(self, product_id: int) -> None:
    """Run catalog enrichment for a single product listing."""
    try:
        CatalogEnrichmentService.enrich(product_id)
    except EnrichmentError as exc:
        logger.error("Enrichment task failed product=%s: %s", product_id, exc)
        raise self.retry(exc=exc) from exc
