"""Unit tests for catalog enrichment pipeline."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.products.enrichment.heuristic import enrich_without_llm
from apps.products.enrichment.image_quality import score_image_file
from apps.products.enrichment.service import CatalogEnrichmentService
from apps.products.models import Category, Product, Store
from apps.products.services import ProductService, StoreService

User = get_user_model()


def _make_user(phone: str) -> User:
    return User.objects.create_user(
        phone_number=phone,
        password="SecurePass123!",
        role="VENDOR",
    )


def _make_category(name: str = "Electronics") -> Category:
    return Category.objects.create(name=name)


def _make_store(owner: User) -> Store:
    store = StoreService.register_store(
        owner=owner,
        validated_data={
            "name": "Enrich Store",
            "business_type": Store.BusinessType.INDIVIDUAL,
            "nrc_or_reg_no": "123456/10/1",
            "id_document": SimpleUploadedFile("id.pdf", b"fake", content_type="application/pdf"),
            "business_address": "Lusaka",
            "phone_number": owner.phone_number,
            "payout_account": "0977000001",
            "payout_provider": Store.PayoutProvider.MTN,
        },
    )
    store.status = Store.Status.APPROVED
    store.save(update_fields=["status"])
    return store


def _make_product(store: Store, category: Category) -> Product:
    return ProductService.create_product(
        store=store,
        validated_data={
            "name": "samsung galaxy a15",
            "description": "good phone",
            "category": category,
            "price": Decimal("3500.00"),
            "condition": Product.Condition.NEW,
            "initial_quantity": 5,
            "track_inventory": True,
        },
    )


class HeuristicEnrichmentTests(TestCase):
    def test_enrich_without_llm_populates_seo_fields(self):
        vendor = _make_user("+260977200001")
        category = _make_category()
        store = _make_store(vendor)
        product = _make_product(store, category)

        payload = enrich_without_llm(product, [category])

        self.assertTrue(payload["enhanced_title"])
        self.assertIn("description_en", payload)
        self.assertTrue(payload["search_keywords"])
        self.assertEqual(payload["category_id"], category.pk)
        self.assertFalse(payload["llm_used"])


class ImageQualityTests(TestCase):
    def test_score_image_file_returns_scores(self):
        import tempfile
        from pathlib import Path

        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.jpg"
            Image.new("RGB", (900, 900), color=(128, 128, 128)).save(path)
            result = score_image_file(path)

        self.assertGreater(result["overall_score"], 0)
        self.assertEqual(result["width"], 900)


@override_settings(CATALOG_ENRICHMENT_ENABLED=True)
class CatalogEnrichmentServiceTests(TestCase):
    @patch("apps.products.enrichment.service.OllamaLLMClient")
    def test_enrich_uses_heuristic_when_ollama_unavailable(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.is_available.return_value = False
        mock_client_cls.return_value = mock_client

        vendor = _make_user("+260977200002")
        category = _make_category("Phones")
        store = _make_store(vendor)
        product = _make_product(store, category)

        enriched = CatalogEnrichmentService.enrich(product.pk)

        self.assertEqual(enriched.enrichment_status, Product.EnrichmentStatus.COMPLETED)
        self.assertTrue(enriched.ai_enhanced_title)
        self.assertIn("en", enriched.descriptions_i18n)
        self.assertTrue(enriched.meta_title)

    @patch("apps.products.enrichment.service.OllamaLLMClient")
    def test_apply_suggestions_updates_live_fields(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.is_available.return_value = False
        mock_client_cls.return_value = mock_client

        vendor = _make_user("+260977200003")
        category = _make_category("Accessories")
        alt_category = _make_category("Gadgets")
        store = _make_store(vendor)
        product = _make_product(store, category)

        enriched = CatalogEnrichmentService.enrich(product.pk)
        enriched.suggested_category = alt_category
        enriched.save(update_fields=["suggested_category"])

        CatalogEnrichmentService.apply_suggestions(
            enriched,
            ["title", "description", "category"],
        )
        enriched.refresh_from_db()

        self.assertEqual(enriched.name, enriched.ai_enhanced_title)
        self.assertEqual(enriched.description, enriched.descriptions_i18n["en"])
        self.assertEqual(enriched.category_id, alt_category.pk)


class PublicProductSerializerTests(TestCase):
    def test_enriched_fields_exposed_when_completed(self):
        from apps.products.serializers import PublicProductDetailSerializer

        vendor = _make_user("+260977200004")
        category = _make_category("Phones")
        store = _make_store(vendor)
        product = _make_product(store, category)
        product.enrichment_status = Product.EnrichmentStatus.COMPLETED
        product.ai_features = ["Dual SIM", "Fast charging"]
        product.ai_specs = {"storage": "128GB"}
        product.suggested_tags = ["smartphone", "android"]
        product.descriptions_i18n = {"en": "Great phone", "fr": "Bon téléphone"}
        product.meta_title = "Samsung A15 | Lingi7"
        product.meta_description = "Buy Samsung A15 with escrow protection."
        product.save()

        data = PublicProductDetailSerializer(product).data
        self.assertEqual(data["features"], ["Dual SIM", "Fast charging"])
        self.assertEqual(data["specs"]["storage"], "128GB")
        self.assertEqual(data["tags"], ["smartphone", "android"])
        self.assertEqual(data["meta_title"], "Samsung A15 | Lingi7")

    def test_enriched_fields_hidden_when_pending(self):
        from apps.products.serializers import PublicProductDetailSerializer

        vendor = _make_user("+260977200005")
        category = _make_category("Tablets")
        store = _make_store(vendor)
        product = _make_product(store, category)
        product.ai_features = ["Should not show"]
        product.save()

        data = PublicProductDetailSerializer(product).data
        self.assertEqual(data["features"], [])
        self.assertEqual(data["tags"], [])
        self.assertEqual(data["meta_title"], product.name)
