"""
Security regression tests for order pricing and IDOR controls.
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.orders.models import OrderServiceError
from apps.orders.services import OrderService
from apps.users.models import KYCStatus


@pytest.mark.django_db
class TestServerSidePricing:
    def test_rejects_client_unit_price(self, buyer, seller, catalog_products):
        p1, _ = catalog_products
        order = OrderService.create_order(
            buyer=buyer,
            seller=seller,
            lines=[{"product_id": p1.pk, "quantity": 1}],
        )
        assert order.lines.first().unit_price == Decimal("250.00")

    def test_tampered_product_id_rejected(self, buyer, seller, catalog_products):
        with pytest.raises(OrderServiceError, match="not found"):
            OrderService.create_order(
                buyer=buyer,
                seller=seller,
                lines=[{"product_id": 99999, "quantity": 1}],
            )


@pytest.mark.django_db
class TestOrderIDOR:
    def test_stranger_cannot_cancel_buyer_order(
        self, draft_order, buyer, seller, sample_lines
    ):
        from apps.users.models import User

        stranger = User.objects.create_user(
            phone_number="+260977777001",
            password="testpass123",
            full_name="Stranger",
            kyc_status=KYCStatus.VERIFIED,
        )
        with pytest.raises(PermissionDenied):
            OrderService.cancel_order(order=draft_order, actor=stranger)

    def test_complete_order_requires_party(self, delivered_order, buyer, seller):
        from apps.users.models import User

        stranger = User.objects.create_user(
            phone_number="+260977777002",
            password="testpass123",
            full_name="Stranger",
            kyc_status=KYCStatus.VERIFIED,
        )
        with pytest.raises(OrderServiceError, match="buyer, seller, or admin"):
            with patch("apps.orders.services.EscrowService.release_funds"):
                OrderService.complete_order(order=delivered_order, actor=stranger)


@pytest.mark.django_db
class TestCanTransactAPI:
    def test_unverified_buyer_cannot_create_order(self, seller, catalog_products):
        from apps.products.models import Product
        from apps.users.models import User

        p1 = catalog_products[0]
        unverified = User.objects.create_user(
            phone_number="+260977777003",
            password="testpass123",
            full_name="Unverified",
            kyc_status=KYCStatus.UNVERIFIED,
        )
        client = APIClient()
        client.force_authenticate(user=unverified)
        response = client.post(
            "/api/v1/orders/",
            {
                "seller_id": str(seller.id),
                "lines": [{"product_id": p1.pk, "quantity": 1}],
                "fulfilment_type": "STANDARD_DELIVERY",
                "delivery_address": "Lusaka",
            },
            format="json",
        )
        assert response.status_code == 403
