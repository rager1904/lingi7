"""
apps/orders/tests/conftest.py

Shared fixtures for orders test suite.
All tests use DB transactions that are rolled back per test.
"""
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.orders.services import OrderService
from apps.products.models import Category, InventoryRecord, Product, Store
from apps.users.models import KYCStatus, UserRole


_phone_counter = 1000


def _next_phone():
    global _phone_counter
    _phone_counter += 1
    return f"+2609{_phone_counter:08d}"


@pytest.fixture
def admin_user(db):
    from apps.users.models import User

    u = User.objects.create_user(
        phone_number=_next_phone(),
        password="testpass123",
        full_name="Admin User",
        role=UserRole.ADMIN,
        kyc_status=KYCStatus.VERIFIED,
    )
    u.is_staff = True
    u.save()
    return u


@pytest.fixture
def buyer(db):
    from apps.users.models import User

    return User.objects.create_user(
        phone_number=_next_phone(),
        password="testpass123",
        full_name="Test Buyer",
        kyc_status=KYCStatus.VERIFIED,
    )


@pytest.fixture
def category(db):
    return Category.objects.create(name="Test Category")


@pytest.fixture
def seller(db, category):
    from apps.users.models import User

    user = User.objects.create_user(
        phone_number=_next_phone(),
        password="testpass123",
        full_name="Test Seller",
        role=UserRole.VENDOR,
        kyc_status=KYCStatus.VERIFIED,
    )
    Store.objects.create(
        owner=user,
        name="Test Store",
        slug=f"test-store-{user.id}",
        status=Store.Status.APPROVED,
        nrc_or_reg_no="123456/10/1",
        business_address="Plot 1, Cairo Road, Lusaka",
        phone_number=user.phone_number,
        payout_account="0977000001",
        payout_provider=Store.PayoutProvider.MTN,
    )
    return user


@pytest.fixture
def catalog_products(db, seller, category):
    store = seller.store
    p1 = Product.objects.create(
        store=store,
        category=category,
        name="Zambian Chitenge Fabric",
        sku="SKU-001",
        price=Decimal("250.00"),
        status=Product.Status.APPROVED,
        condition=Product.Condition.NEW,
    )
    p2 = Product.objects.create(
        store=store,
        category=category,
        name="Leather Belt",
        sku="SKU-002",
        price=Decimal("85.00"),
        status=Product.Status.APPROVED,
        condition=Product.Condition.NEW,
    )
    InventoryRecord.objects.create(product=p1, quantity_available=100)
    InventoryRecord.objects.create(product=p2, quantity_available=100)
    return p1, p2


@pytest.fixture
def sample_lines(catalog_products):
    p1, p2 = catalog_products
    return [
        {"product_id": p1.pk, "quantity": 2},
        {"product_id": p2.pk, "quantity": 1},
    ]


@pytest.fixture
def draft_order(db, buyer, seller, sample_lines):
    return OrderService.create_order(
        buyer=buyer,
        seller=seller,
        lines=sample_lines,
        delivery_address="Plot 15, Cairo Road, Lusaka",
    )


@pytest.fixture
def pending_order(db, draft_order, buyer):
    return OrderService.submit_order(order=draft_order, actor=buyer)


@pytest.fixture
def payment_received_order(db, pending_order, buyer):
    mock_payment = MagicMock()
    mock_payment.id = uuid.uuid4()
    mock_payment.idempotency_key = "test-idemp-key-001"
    mock_payment.amount = pending_order.total_amount
    mock_payment.provider = "MTN_MOMO"
    mock_payment.provider_reference = "MOMO-REF-001"

    with patch("apps.orders.services.EscrowService.hold_funds"):
        order = OrderService.confirm_payment(
            order=pending_order,
            payment_attempt=mock_payment,
            actor=buyer,
        )
    return order


@pytest.fixture
def processing_order(db, payment_received_order, seller):
    return OrderService.acknowledge_order(
        order=payment_received_order, actor=seller
    )


@pytest.fixture
def shipped_order(db, processing_order, seller):
    with patch("apps.orders.services.EscrowService.mark_in_transit"):
        return OrderService.ship_order(
            order=processing_order,
            actor=seller,
            carrier="Zampost",
            tracking_number="ZP-12345",
        )


@pytest.fixture
def delivered_order(db, shipped_order, buyer):
    with patch("apps.orders.services.EscrowService.mark_delivered"):
        return OrderService.confirm_delivery(order=shipped_order, actor=buyer)
