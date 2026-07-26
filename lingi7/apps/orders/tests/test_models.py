"""
apps/orders/tests/test_models.py

Unit tests for Order models, state machine, and immutability guards.
"""
import pytest
from decimal import Decimal

from apps.orders.constants import OrderStatus, ORDER_TRANSITIONS
from apps.orders.models import (
    Order,
    OrderEvent,
    ImmutableOrderEventError,
    InvalidOrderTransitionError,
)


@pytest.mark.django_db
class TestOrderStateTransitions:
    def test_all_defined_transitions_are_valid(self, draft_order):
        """Every transition in ORDER_TRANSITIONS must be reachable via can_transition_to."""
        for from_status, targets in ORDER_TRANSITIONS.items():
            draft_order.status = from_status
            for to_status in targets:
                assert draft_order.can_transition_to(to_status), (
                    f"{from_status} → {to_status} should be allowed"
                )

    def test_invalid_transition_raises(self, draft_order):
        draft_order.status = OrderStatus.COMPLETED
        assert not draft_order.can_transition_to(OrderStatus.DRAFT)

    def test_assert_transition_raises_on_invalid(self, draft_order):
        draft_order.status = OrderStatus.COMPLETED
        with pytest.raises(InvalidOrderTransitionError):
            draft_order.assert_transition(OrderStatus.DRAFT)

    def test_terminal_states_have_no_transitions(self):
        for terminal in OrderStatus.TERMINAL:
            assert ORDER_TRANSITIONS[terminal] == set(), (
                f"{terminal} should have no transitions"
            )

    def test_is_terminal_property(self, draft_order):
        draft_order.status = OrderStatus.COMPLETED
        assert draft_order.is_terminal

        draft_order.status = OrderStatus.DRAFT
        assert not draft_order.is_terminal


@pytest.mark.django_db
class TestOrderLineImmutability:
    def test_order_line_totals(self, draft_order):
        """Line totals must equal unit_price * quantity."""
        for line in draft_order.lines.all():
            assert line.line_total == line.unit_price * line.quantity

    def test_order_subtotal_matches_lines(self, draft_order):
        expected = sum(l.unit_price * l.quantity for l in draft_order.lines.all())
        assert draft_order.subtotal == expected


@pytest.mark.django_db
class TestOrderEventImmutability:
    def test_order_event_cannot_be_modified(self, draft_order, buyer):
        event = OrderEvent.objects.create(
            order=draft_order,
            from_status=OrderStatus.DRAFT,
            to_status=OrderStatus.PENDING_PAYMENT,
            triggered_by=buyer,
        )
        with pytest.raises(ImmutableOrderEventError):
            event.note = "Modified"
            event.save()

    def test_order_event_cannot_be_deleted(self, draft_order, buyer):
        event = OrderEvent.objects.create(
            order=draft_order,
            from_status=OrderStatus.DRAFT,
            to_status=OrderStatus.PENDING_PAYMENT,
            triggered_by=buyer,
        )
        with pytest.raises(ImmutableOrderEventError):
            event.delete()


@pytest.mark.django_db
class TestOrderReference:
    def test_reference_is_unique(self, buyer, seller, sample_lines):
        from apps.orders.services import OrderService
        orders = [
            OrderService.create_order(buyer=buyer, seller=seller, lines=sample_lines)
            for _ in range(5)
        ]
        refs = [o.reference for o in orders]
        assert len(refs) == len(set(refs))

    def test_reference_prefix(self, draft_order):
        assert draft_order.reference.startswith("LG7-")


@pytest.mark.django_db
class TestHasActiveDispute:
    def test_no_dispute_initially(self, draft_order):
        assert not draft_order.has_active_dispute
