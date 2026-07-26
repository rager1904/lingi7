"""Public storefront API safety and visibility tests."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.products.models import Category, Product, Store

User = get_user_model()


class PublicStorefrontApiTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.category = Category.objects.create(name="Electronics")
        owner = User.objects.create_user(
            phone_number="+260977111222", password="SecurePass123!", role="VENDOR"
        )
        self.live_store = Store.objects.create(
            owner=owner,
            name="Live Electronics", slug="live-electronics", status=Store.Status.APPROVED,
            nrc_or_reg_no="123456/10/1", business_address="Lusaka", phone_number=owner.phone_number,
        )
        Product.objects.create(
            store=self.live_store, category=self.category, name="Live phone", slug="live-phone",
            price=Decimal("100.00"), status=Product.Status.APPROVED, condition=Product.Condition.NEW,
        )
        pending_owner = User.objects.create_user(
            phone_number="+260977111223", password="SecurePass123!", role="VENDOR"
        )
        self.pending_store = Store.objects.create(
            owner=pending_owner, name="Pending Electronics", slug="pending-electronics", status=Store.Status.PENDING,
            nrc_or_reg_no="123456/10/2", business_address="Lusaka", phone_number=pending_owner.phone_number,
        )

    def test_only_approved_stores_are_listed_with_safe_fields(self) -> None:
        response = self.client.get("/api/v1/products/stores/")
        self.assertEqual(response.status_code, 200)
        stores = response.data["results"]
        self.assertEqual([item["slug"] for item in stores], ["live-electronics"])
        self.assertEqual(stores[0]["product_count"], 1)
        self.assertNotIn("payout_account", stores[0])
        self.assertNotIn("owner", stores[0])
        self.assertNotIn("nrc_or_reg_no", stores[0])

    def test_pending_store_is_not_publicly_retrievable(self) -> None:
        response = self.client.get("/api/v1/products/stores/pending-electronics/")
        self.assertEqual(response.status_code, 404)

    def test_product_store_filter_returns_only_requested_store(self) -> None:
        response = self.client.get("/api/v1/products/products/?store=live-electronics")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["slug"] for item in response.data["results"]], ["live-phone"])
