"""
apps/orders/tests/test_services.py

Integration tests for OrderService — full lifecycle,
dispute handling, fee calculation, and error paths.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from apps.orders.constants import (
    DisputeReason,
    DisputeResolution,
    FulfilmentType,
    OrderStatus,
)
from apps.orders.models import (
    InvalidOrderTransitionError,
    Order,
    OrderDispute,
    OrderEvent,
    OrderServiceError,
    OrderShipment,
)
from apps.orders.services import FeeCalculator, OrderService


# ─────────────────────────────── FeeCalculator ───────────────────────────────

class TestFeeCalculator:
    def test_tier_1_fee(self):
        """0–500 ZMW: 3.5%"""
        assert FeeCalculator.calculate(Decimal("400.00")) == Decimal("14.00")

    def test_tier_2_fee(self):
        """501–5000 ZMW: 2.5%"""
        assert FeeCalculator.calculate(Decimal("1000.00")) == Decimal("25.00")

    def test_tier_3_fee(self):
        """5001+ ZMW: 1.5%"""
        assert FeeCalculator.calculate(Decimal("10000.00")) == Decimal("150.00")

    def test_boundary_500(self):
        assert FeeCalculator.calculate(Decimal("500.00")) == Decimal("17.50")

    def test_boundary_501(self):
        assert FeeCalculator.calculate(Decimal("501.00")) == Decimal("12.53")

    def test_fee_is_decimal_precision(self):
        result = FeeCalculator.calculate(Decimal("333.33"))
        assert result == result.quantize(Decimal("0.01"))


# ─────────────────────────────── Order Creation ──────────────────────────────

@pytest.mark.django_db
class TestCreateOrder:
    def test_create_draft_order(self, buyer, seller, sample_lines):
        order = OrderService.create_order(buyer=buyer, seller=seller, lines=sample_lines)
        assert order.status == OrderStatus.DRAFT
        assert order.buyer == buyer
        assert order.seller == seller
        assert order.lines.count() == 2

    def test_totals_calculated_correctly(self, buyer, seller, sample_lines):
        order = OrderService.create_order(buyer=buyer, seller=seller, lines=sample_lines)
        expected_subtotal = Decimal("585.00")  # 250*2 + 85*1
        assert order.subtotal == expected_subtotal
        assert order.platform_fee == FeeCalculator.calculate(expected_subtotal)
        assert order.total_amount == order.subtotal + order.platform_fee

    def test_buyer_cannot_be_seller(self, buyer, sample_lines):
        with pytest.raises(OrderServiceError, match="same user"):
            OrderService.create_order(buyer=buyer, seller=buyer, lines=sample_lines)

    def test_empty_lines_raises(self, buyer, seller):
        with pytest.raises(OrderServiceError, match="at least one"):
            OrderService.create_order(buyer=buyer, seller=seller, lines=[])

    def test_negative_price_raises(self, buyer, seller):
        with pytest.raises(OrderServiceError, match="positive"):
            OrderService.create_order(
                buyer=buyer, seller=seller,
                lines=[{"product_name": "X", "unit_price": Decimal("-10.00"), "quantity": 1}]
            )

    def test_zero_quantity_raises(self, buyer, seller):
        with pytest.raises(OrderServiceError, match=">= 1"):
            OrderService.create_order(
                buyer=buyer, seller=seller,
                lines=[{"product_name": "X", "unit_price": Decimal("10.00"), "quantity": 0}]
            )

    def test_currency_defaults_zmw(self, draft_order):
        assert draft_order.currency == "ZMW"

    def test_fulfilment_type_stored(self, buyer, seller, sample_lines):
        order = OrderService.create_order(
            buyer=buyer, seller=seller, lines=sample_lines,
            fulfilment_type=FulfilmentType.PICKUP
        )
        assert order.fulfilment_type == FulfilmentType.PICKUP


# ─────────────────────────────── Submit Order ────────────────────────────────

@pytest.mark.django_db
class TestSubmitOrder:
    def test_submit_transitions_to_pending(self, draft_order, buyer):
        mock_escrow = MagicMock()
        mock_escrow.id = "test-escrow-id"

        with patch("apps.orders.services.EscrowService.create_escrow_account", return_value=mock_escrow):
            order = OrderService.submit_order(order=draft_order, actor=buyer)

        assert order.status == OrderStatus.PENDING_PAYMENT
        assert order.submitted_at is not None

    def test_submit_creates_order_event(self, draft_order, buyer):
        mock_escrow = MagicMock()
        mock_escrow.id = "test-escrow-id-2"

        with patch("apps.orders.services.EscrowService.create_escrow_account", return_value=mock_escrow):
            OrderService.submit_order(order=draft_order, actor=buyer)

        assert OrderEvent.objects.filter(
            order=draft_order,
            to_status=OrderStatus.PENDING_PAYMENT,
        ).exists()

    def test_cannot_submit_non_draft(self, pending_order, buyer):
        with pytest.raises(InvalidOrderTransitionError):
            OrderService.submit_order(order=pending_order, actor=buyer)


# ─────────────────────────────── Confirm Payment ────────────────────────────

@pytest.mark.django_db
class TestConfirmPayment:
    def test_confirm_transitions_to_payment_received(self, pending_order, buyer):
        mock_attempt = MagicMock()
        mock_attempt.id = "pay-001"
        mock_attempt.idempotency_key = "idem-001"

        with patch("apps.orders.services.EscrowService.hold_funds"):
            order = OrderService.confirm_payment(
                order=pending_order,
                payment_attempt=mock_attempt,
                actor=buyer,
            )

        assert order.status == OrderStatus.PAYMENT_RECEIVED
        assert order.paid_at is not None

    def test_escrow_hold_called(self, pending_order, buyer):
        mock_attempt = MagicMock()
        mock_attempt.id = "pay-002"
        mock_attempt.idempotency_key = "idem-002"

        with patch("apps.orders.services.EscrowService.hold_funds") as mock_hold:
            OrderService.confirm_payment(
                order=pending_order,
                payment_attempt=mock_attempt,
                actor=buyer,
            )
            assert mock_hold.called


# ─────────────────────────────── Acknowledge ─────────────────────────────────

@pytest.mark.django_db
class TestAcknowledgeOrder:
    def test_seller_can_acknowledge(self, payment_received_order, seller):
        order = OrderService.acknowledge_order(order=payment_received_order, actor=seller)
        assert order.status == OrderStatus.PROCESSING

    def test_buyer_cannot_acknowledge(self, payment_received_order, buyer):
        with pytest.raises(OrderServiceError, match="seller or admin"):
            OrderService.acknowledge_order(order=payment_received_order, actor=buyer)

    def test_admin_can_acknowledge(self, payment_received_order, admin_user):
        order = OrderService.acknowledge_order(order=payment_received_order, actor=admin_user)
        assert order.status == OrderStatus.PROCESSING


# ─────────────────────────────── Ship ────────────────────────────────────────

@pytest.mark.django_db
class TestShipOrder:
    def test_ship_creates_shipment(self, processing_order, seller):
        order = OrderService.ship_order(
            order=processing_order,
            actor=seller,
            carrier="Zampost",
            tracking_number="ZP-99999",
        )
        assert order.status == OrderStatus.SHIPPED
        assert OrderShipment.objects.filter(order=order).exists()

    def test_ship_requires_carrier(self, processing_order, seller):
        with pytest.raises(OrderServiceError, match="Carrier"):
            OrderService.ship_order(
                order=processing_order, actor=seller, carrier=""
            )

    def test_buyer_cannot_ship(self, processing_order, buyer):
        with pytest.raises(OrderServiceError, match="seller or admin"):
            OrderService.ship_order(
                order=processing_order, actor=buyer, carrier="Zampost"
            )


# ─────────────────────────────── Deliver ─────────────────────────────────────

@pytest.mark.django_db
class TestConfirmDelivery:
    def test_buyer_confirms_delivery(self, shipped_order, buyer):
        order = OrderService.confirm_delivery(order=shipped_order, actor=buyer)
        assert order.status == OrderStatus.DELIVERED

    def test_seller_cannot_confirm_delivery(self, shipped_order, seller):
        with pytest.raises(OrderServiceError, match="buyer or admin"):
            OrderService.confirm_delivery(order=shipped_order, actor=seller)


# ─────────────────────────────── Complete ────────────────────────────────────

@pytest.mark.django_db
class TestCompleteOrder:
    def test_complete_releases_escrow(self, delivered_order, buyer):
        with patch("apps.orders.services.EscrowService.release_funds") as mock_release:
            order = OrderService.complete_order(order=delivered_order, actor=buyer)
            assert order.status == OrderStatus.COMPLETED
            assert order.completed_at is not None
            assert mock_release.called

    def test_cannot_complete_from_processing(self, processing_order, buyer):
        with pytest.raises(InvalidOrderTransitionError):
            OrderService.complete_order(order=processing_order, actor=buyer)


# ─────────────────────────────── Cancel ──────────────────────────────────────

@pytest.mark.django_db
class TestCancelOrder:
    def test_buyer_can_cancel_draft(self, draft_order, buyer):
        order = OrderService.cancel_order(order=draft_order, actor=buyer)
        assert order.status == OrderStatus.CANCELLED
        assert order.cancelled_at is not None

    def test_buyer_cannot_cancel_after_payment(self, payment_received_order, buyer):
        with pytest.raises(OrderServiceError, match="Buyers can only cancel"):
            OrderService.cancel_order(order=payment_received_order, actor=buyer)

    def test_admin_can_cancel_processing(self, processing_order, admin_user):
        order = OrderService.cancel_order(order=processing_order, actor=admin_user, reason="Fraud detected")
        assert order.status == OrderStatus.CANCELLED

    def test_event_recorded_on_cancel(self, draft_order, buyer):
        OrderService.cancel_order(order=draft_order, actor=buyer, reason="Changed mind")
        assert OrderEvent.objects.filter(
            order=draft_order, to_status=OrderStatus.CANCELLED
        ).exists()


# ─────────────────────────────── Disputes ────────────────────────────────────

@pytest.mark.django_db
class TestRaiseDispute:
    def test_buyer_can_raise_dispute(self, delivered_order, buyer):
        dispute = OrderService.raise_dispute(
            order=delivered_order,
            raised_by=buyer,
            reason=DisputeReason.ITEM_NOT_AS_DESC,
            description="The product looks completely different from the listing images.",
        )
        assert isinstance(dispute, OrderDispute)
        assert delivered_order.status == OrderStatus.DISPUTED

    def test_dispute_creates_event(self, delivered_order, buyer):
        OrderService.raise_dispute(
            order=delivered_order,
            raised_by=buyer,
            reason=DisputeReason.ITEM_NOT_RECEIVED,
            description="Package never arrived after 14 days.",
        )
        assert OrderEvent.objects.filter(
            order=delivered_order, to_status=OrderStatus.DISPUTED
        ).exists()

    def test_invalid_reason_raises(self, delivered_order, buyer):
        with pytest.raises(OrderServiceError, match="Invalid dispute reason"):
            OrderService.raise_dispute(
                order=delivered_order,
                raised_by=buyer,
                reason="INVALID_REASON",
                description="Some description with enough characters.",
            )

    def test_unrelated_user_cannot_raise_dispute(self, delivered_order, admin_user):
        from apps.users.models import User
        stranger = User.objects.create_user(
            phone_number="+260911111111",
            password="pass",
            full_name="Stranger",
        )
        with pytest.raises(OrderServiceError, match="buyer, seller, or admin"):
            OrderService.raise_dispute(
                order=delivered_order,
                raised_by=stranger,
                reason=DisputeReason.OTHER,
                description="Trying to interfere with order that is not mine.",
            )


@pytest.mark.django_db
class TestResolveDispute:
    def _dispute(self, delivered_order, buyer):
        return OrderService.raise_dispute(
            order=delivered_order,
            raised_by=buyer,
            reason=DisputeReason.DAMAGED_ITEM,
            description="Item arrived with visible damage to the packaging and contents.",
        )

    def test_refund_buyer_resolution(self, delivered_order, buyer, admin_user):
        dispute = self._dispute(delivered_order, buyer)
        with patch("apps.orders.services.EscrowService.refund") as mock_refund:
            result = OrderService.resolve_dispute(
                dispute=dispute,
                resolved_by=admin_user,
                resolution=DisputeResolution.REFUND_BUYER,
            )
            assert mock_refund.called
        assert result.resolution == DisputeResolution.REFUND_BUYER
        assert result.resolved_at is not None
        delivered_order.refresh_from_db()
        assert delivered_order.status == OrderStatus.REFUNDED

    def test_release_seller_resolution(self, delivered_order, buyer, admin_user):
        dispute = self._dispute(delivered_order, buyer)
        with patch("apps.orders.services.EscrowService.release_funds") as mock_release:
            result = OrderService.resolve_dispute(
                dispute=dispute,
                resolved_by=admin_user,
                resolution=DisputeResolution.RELEASE_SELLER,
            )
            assert mock_release.called
        delivered_order.refresh_from_db()
        assert delivered_order.status == OrderStatus.COMPLETED

    def test_partial_refund_requires_amount(self, delivered_order, buyer, admin_user):
        dispute = self._dispute(delivered_order, buyer)
        with pytest.raises(OrderServiceError, match="refund_amount required"):
            OrderService.resolve_dispute(
                dispute=dispute,
                resolved_by=admin_user,
                resolution=DisputeResolution.PARTIAL_REFUND,
            )

    def test_non_admin_cannot_resolve(self, delivered_order, buyer):
        dispute = self._dispute(delivered_order, buyer)
        with pytest.raises(OrderServiceError, match="Only admin"):
            OrderService.resolve_dispute(
                dispute=dispute,
                resolved_by=buyer,
                resolution=DisputeResolution.REFUND_BUYER,
            )

    def test_cannot_resolve_already_resolved(self, delivered_order, buyer, admin_user):
        dispute = self._dispute(delivered_order, buyer)
        with patch("apps.orders.services.EscrowService.refund"):
            OrderService.resolve_dispute(
                dispute=dispute,
                resolved_by=admin_user,
                resolution=DisputeResolution.REFUND_BUYER,
            )
        with pytest.raises(OrderServiceError, match="already resolved"):
            OrderService.resolve_dispute(
                dispute=dispute,
                resolved_by=admin_user,
                resolution=DisputeResolution.REFUND_BUYER,
            )


# ─────────────────────────────── Audit Trail ─────────────────────────────────

@pytest.mark.django_db
class TestOrderEventTrail:
    def test_full_happy_path_events(self, delivered_order):
        """DRAFT → PENDING → PAYMENT_RECEIVED → PROCESSING → SHIPPED → DELIVERED"""
        events = OrderEvent.objects.filter(order=delivered_order).order_by("created_at")
        statuses = [e.to_status for e in events]
        assert OrderStatus.PENDING_PAYMENT in statuses
        assert OrderStatus.PAYMENT_RECEIVED in statuses
        assert OrderStatus.PROCESSING in statuses
        assert OrderStatus.SHIPPED in statuses
        assert OrderStatus.DELIVERED in statuses
