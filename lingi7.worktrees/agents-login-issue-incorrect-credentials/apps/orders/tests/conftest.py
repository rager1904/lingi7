"""
apps/orders/tests/conftest.py

Shared fixtures for orders test suite.
All tests use DB transactions that are rolled back per test.
"""
import pytest
from decimal import Decimal

from django.utils import timezone

from apps.orders.constants import FulfilmentType, OrderStatus, DisputeReason
from apps.orders.models import Order, OrderLine, OrderEvent, OrderDispute
from apps.orders.services import OrderService


# ─────────────────────────────── Counters ────────────────────────────────────

_phone_counter = 1000


def _next_phone():
    global _phone_counter
    _phone_counter += 1
    return f"+2609{_phone_counter:08d}"


# ─────────────────────────────── User Fixtures ───────────────────────────────

@pytest.fixture
def buyer(db):
    from apps.users.models import User
    return User.objects.create_user(
        phone_number=_next_phone(),
        password="testpass123",
        full_name="Test Buyer",
    )


@pytest.fixture
def seller(db):
    from apps.users.models import User
    return User.objects.create_user(
        phone_number=_next_phone(),
        password="testpass123",
        full_name="Test Seller",
    )


@pytest.fixture
def admin_user(db):
    from apps.users.models import User
    u = User.objects.create_user(
        phone_number=_next_phone(),
        password="testpass123",
        full_name="Admin User",
    )
    u.is_staff = True
    u.save()
    return u


# ─────────────────────────────── Line Data ───────────────────────────────────

@pytest.fixture
def sample_lines():
    return [
        {
            "product_name": "Zambian Chitenge Fabric",
            "product_id": "SKU-001",
            "unit_price": Decimal("250.00"),
            "quantity": 2,
        },
        {
            "product_name": "Leather Belt",
            "product_id": "SKU-002",
            "unit_price": Decimal("85.00"),
            "quantity": 1,
        },
    ]


# ─────────────────────────────── Order Fixtures ──────────────────────────────

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
    """
    Mocked PENDING_PAYMENT order — bypasses EscrowService.create_escrow_account
    by patching the external dependency.
    """
    from unittest.mock import MagicMock, patch

    mock_escrow = MagicMock()
    mock_escrow.id = "00000000-0000-0000-0000-000000000001"

    with patch("apps.orders.services.EscrowService.create_escrow_account", return_value=mock_escrow):
        order = OrderService.submit_order(order=draft_order, actor=buyer)
    return order


@pytest.fixture
def payment_received_order(db, pending_order, buyer):
    """Order with payment confirmed (PAYMENT_RECEIVED)."""
    from unittest.mock import MagicMock, patch

    mock_payment = MagicMock()
    mock_payment.id = "00000000-0000-0000-0000-000000000002"
    mock_payment.idempotency_key = "test-idemp-key-001"

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
    return OrderService.ship_order(
        order=processing_order,
        actor=seller,
        carrier="Zampost",
        tracking_number="ZP-12345",
    )


@pytest.fixture
def delivered_order(db, shipped_order, buyer):
    return OrderService.confirm_delivery(order=shipped_order, actor=buyer)
