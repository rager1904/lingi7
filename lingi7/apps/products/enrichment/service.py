"""
CatalogEnrichmentService — orchestrates LLM, VLM, and image-quality enrichment.

Designed to run inside Celery workers. When Ollama is unavailable, falls back
to heuristic enrichment so vendors still receive SEO and i18n scaffolding.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.products.assistant_index import AssistantCatalogIndexer
from apps.products.enrichment.external_service import ExternalCatalogEnrichmentClient
from apps.products.enrichment.heuristic import enrich_without_llm
from apps.products.enrichment.image_quality import score_product_images
from apps.products.enrichment.llm_client import OllamaLLMClient
from apps.products.enrichment.prompts import (
    CATEGORY_PROMPT,
    DESCRIPTION_PROMPT,
    SYSTEM_PROMPT,
    VISION_PROMPT,
)
from apps.products.enrichment.threed import generate_3d_preview
from apps.products.exceptions import EnrichmentError
from apps.products.models import Category, Product

logger = logging.getLogger(__name__)

APPLY_FIELD_CHOICES = ("title", "description", "category", "seo")


class CatalogEnrichmentService:
    """Entry point for product catalog enrichment."""

    @staticmethod
    @transaction.atomic
    def queue_enrichment(product_id: int) -> Product:
        if not settings.CATALOG_ENRICHMENT_ENABLED:
            product = Product.objects.get(pk=product_id)
            product.enrichment_status = Product.EnrichmentStatus.DISABLED
            product.save(update_fields=["enrichment_status", "updated_at"])
            return product

        from apps.products.tasks import enrich_product_task

        product = Product.objects.select_for_update().get(pk=product_id)
        product.enrichment_status = Product.EnrichmentStatus.PENDING
        product.enrichment_error = ""
        product.save(update_fields=["enrichment_status", "enrichment_error", "updated_at"])
        enrich_product_task.delay(product_id)
        return product

    @staticmethod
    @transaction.atomic
    def enrich(product_id: int) -> Product:
        if not settings.CATALOG_ENRICHMENT_ENABLED:
            raise EnrichmentError("Catalog enrichment is disabled.")

        product = (
            Product.objects.select_for_update()
            .select_related("category", "store")
            .prefetch_related("images")
            .get(pk=product_id)
        )
        product.enrichment_status = Product.EnrichmentStatus.PROCESSING
        product.enrichment_error = ""
        product.save(update_fields=["enrichment_status", "enrichment_error", "updated_at"])

        try:
            payload = CatalogEnrichmentService._build_enrichment_payload(product)
            image_scores = score_product_images(product)
            threed = generate_3d_preview(product)

            product.ai_enhanced_title = payload.get("enhanced_title", "")[:200]
            product.descriptions_i18n = {
                "en": payload.get("description_en", product.description),
                "fr": payload.get("description_fr", ""),
                "sw": payload.get("description_sw", ""),
            }
            product.ai_features = payload.get("features") or []
            product.ai_specs = payload.get("specs") or {}
            product.meta_title = (payload.get("meta_title") or "")[:70]
            product.meta_description = (payload.get("meta_description") or "")[:160]
            product.search_keywords = payload.get("search_keywords") or []
            product.suggested_tags = payload.get("tags") or []

            suggested_category_id = payload.get("category_id")
            if suggested_category_id:
                if Category.objects.filter(pk=suggested_category_id, is_active=True).exists():
                    product.suggested_category_id = suggested_category_id
                else:
                    product.suggested_category_id = product.category_id
            else:
                product.suggested_category_id = product.category_id

            product.image_quality_scores = image_scores
            if threed:
                product.ai_specs = {**product.ai_specs, "threed_preview": threed}

            product.enrichment_status = Product.EnrichmentStatus.COMPLETED
            product.enriched_at = timezone.now()
            product.enrichment_error = ""
            product.save(
                update_fields=[
                    "ai_enhanced_title",
                    "descriptions_i18n",
                    "ai_features",
                    "ai_specs",
                    "meta_title",
                    "meta_description",
                    "search_keywords",
                    "suggested_tags",
                    "suggested_category",
                    "image_quality_scores",
                    "enrichment_status",
                    "enriched_at",
                    "enrichment_error",
                    "updated_at",
                ]
            )
            transaction.on_commit(lambda: AssistantCatalogIndexer.index_product(product))
            logger.info("Catalog enrichment completed: product=%s", product_id)
            return product
        except Exception as exc:
            product.enrichment_status = Product.EnrichmentStatus.FAILED
            product.enrichment_error = str(exc)[:2000]
            product.save(
                update_fields=["enrichment_status", "enrichment_error", "updated_at"]
            )
            logger.exception("Catalog enrichment failed: product=%s", product_id)
            raise EnrichmentError(str(exc)) from exc

    @staticmethod
    @transaction.atomic
    def apply_suggestions(product: Product, fields: list[str]) -> Product:
        allowed = set(APPLY_FIELD_CHOICES)
        unknown = set(fields) - allowed
        if unknown:
            raise EnrichmentError(f"Unknown apply fields: {', '.join(sorted(unknown))}")

        update_fields: list[str] = ["updated_at"]

        if "title" in fields and product.ai_enhanced_title:
            product.name = product.ai_enhanced_title
            update_fields.append("name")

        if "description" in fields:
            en_desc = (product.descriptions_i18n or {}).get("en")
            if en_desc:
                product.description = en_desc
                update_fields.append("description")

        if "category" in fields and product.suggested_category_id:
            product.category_id = product.suggested_category_id
            update_fields.append("category")

        if "seo" in fields:
            # SEO fields are already stored on the product during enrichment;
            # this flag confirms the vendor reviewed them.
            update_fields.extend(["meta_title", "meta_description", "search_keywords"])

        product.save(update_fields=list(dict.fromkeys(update_fields)))
        transaction.on_commit(lambda: AssistantCatalogIndexer.index_product(product))
        return product

    @staticmethod
    @transaction.atomic
    def apply_external_payload(product: Product, payload: dict[str, Any]) -> Product:
        """Persist a workbench enrichment payload on a Django product and index it."""
        categories = list(Category.objects.filter(is_active=True).order_by("name")[:200])
        normalised = CatalogEnrichmentService._normalise_external_payload(
            payload,
            product,
            categories,
        )

        product.ai_enhanced_title = normalised.get("enhanced_title", "")[:200]
        product.descriptions_i18n = {
            "en": normalised.get("description_en", product.description),
            "fr": normalised.get("description_fr", ""),
            "sw": normalised.get("description_sw", ""),
        }
        product.ai_features = normalised.get("features") or []
        product.ai_specs = normalised.get("specs") or {}
        product.meta_title = (normalised.get("meta_title") or "")[:70]
        product.meta_description = (normalised.get("meta_description") or "")[:160]
        product.search_keywords = normalised.get("search_keywords") or []
        product.suggested_tags = normalised.get("tags") or []
        product.suggested_category_id = normalised.get("category_id") or product.category_id
        product.enrichment_status = Product.EnrichmentStatus.COMPLETED
        product.enriched_at = timezone.now()
        product.enrichment_error = ""
        product.save(
            update_fields=[
                "ai_enhanced_title",
                "descriptions_i18n",
                "ai_features",
                "ai_specs",
                "meta_title",
                "meta_description",
                "search_keywords",
                "suggested_tags",
                "suggested_category",
                "enrichment_status",
                "enriched_at",
                "enrichment_error",
                "updated_at",
            ]
        )
        transaction.on_commit(lambda: AssistantCatalogIndexer.index_product(product))
        return product

    @staticmethod
    def _build_enrichment_payload(product: Product) -> dict[str, Any]:
        categories = list(Category.objects.filter(is_active=True).order_by("name")[:200])
        external_payload = ExternalCatalogEnrichmentClient().analyze_product(product)
        if external_payload:
            return CatalogEnrichmentService._normalise_external_payload(
                external_payload,
                product,
                categories,
            )

        client = OllamaLLMClient()

        if not client.is_available():
            logger.info("Ollama unavailable — heuristic enrichment for product=%s", product.pk)
            return enrich_without_llm(product, categories)

        try:
            desc_prompt = DESCRIPTION_PROMPT.format(
                name=product.name,
                category=product.category.name if product.category_id else "",
                condition=product.get_condition_display(),
                description=product.description,
                price=product.price,
            )
            raw_desc = client.complete_text(desc_prompt, system=SYSTEM_PROMPT)
            payload = client.parse_json_response(raw_desc)
            payload["llm_used"] = True

            cat_lines = "\n".join(f"{c.pk}: {c.name}" for c in categories)
            cat_prompt = CATEGORY_PROMPT.format(
                name=product.name,
                description=payload.get("description_en", product.description),
                categories=cat_lines,
            )
            raw_cat = client.complete_text(cat_prompt, system=SYSTEM_PROMPT)
            cat_data = client.parse_json_response(raw_cat)
            payload["category_id"] = cat_data.get("category_id")
            payload["category_confidence"] = cat_data.get("confidence", 0.0)

            primary = product.images.order_by("position").first()
            if primary and primary.image:
                try:
                    image_path = primary.image.path
                    vision_prompt = VISION_PROMPT.format(name=product.name)
                    raw_vision = client.complete_vision(vision_prompt, image_path)
                    vision_data = client.parse_json_response(raw_vision)
                    visible = vision_data.get("visible_features") or []
                    if visible:
                        payload["features"] = list(
                            dict.fromkeys((payload.get("features") or []) + visible)
                        )[:8]
                    alt_text = vision_data.get("suggested_alt_text")
                    if alt_text and not primary.alt_text:
                        primary.alt_text = str(alt_text)[:200]
                        primary.save(update_fields=["alt_text"])
                except (OSError, ValueError, NotImplementedError) as exc:
                    logger.debug("Vision enrichment skipped for product=%s: %s", product.pk, exc)

            return payload
        except Exception as exc:
            logger.warning(
                "LLM enrichment failed for product=%s, using heuristic: %s",
                product.pk,
                exc,
            )
            fallback = enrich_without_llm(product, categories)
            fallback["llm_error"] = str(exc)
            return fallback

    @staticmethod
    def _normalise_external_payload(
        payload: dict[str, Any],
        product: Product,
        categories: list[Category],
    ) -> dict[str, Any]:
        """Map standalone enrichment output into Django product enrichment fields."""
        category_names = [
            str(name).strip().lower()
            for name in payload.get("categories", [])
            if str(name).strip()
        ]
        selected_category_id = product.category_id
        for category in categories:
            name = category.name.strip().lower()
            slug = category.slug.strip().lower()
            if name in category_names or slug in category_names:
                selected_category_id = category.pk
                break

        title = str(payload.get("title") or product.name)
        description = str(payload.get("description") or product.description)
        tags = [str(tag).strip() for tag in payload.get("tags", []) if str(tag).strip()]
        colors = [str(color).strip() for color in payload.get("colors", []) if str(color).strip()]
        enhanced = payload.get("enhanced_product") if isinstance(payload.get("enhanced_product"), dict) else {}
        policy = payload.get("policy_decision") if isinstance(payload.get("policy_decision"), dict) else {}

        features = enhanced.get("highlights") or enhanced.get("features") or tags[:8]
        if not isinstance(features, list):
            features = tags[:8]

        specs: dict[str, Any] = {
            "source": "standalone-enrichment-service",
            "colors": colors,
        }
        if policy:
            specs["policy_decision"] = policy
        if enhanced:
            specs["enhanced_product"] = enhanced

        keywords = list(dict.fromkeys(tags + colors + category_names + [product.name]))
        return {
            "enhanced_title": title,
            "description_en": description,
            "description_fr": "",
            "description_sw": "",
            "features": features[:8],
            "specs": specs,
            "meta_title": title[:70],
            "meta_description": description[:160],
            "search_keywords": keywords[:20],
            "tags": tags[:20],
            "category_id": selected_category_id,
            "llm_used": True,
            "external_service_used": True,
        }
