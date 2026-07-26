"""
Tests for the Shipment state machine.

Covers all valid transitions and asserts all invalid transitions
raise InvalidShipmentTransitionError.

Reference: LG7-BE-009 | apps/logistics/tests/test_state_machine.py
"""

import pytest

from apps.logistics.exceptions import InvalidShipmentTransitionError
from apps.logistics.models import Shipment
from apps.logistics.state_machine import ShipmentStateMachine, VALID_TRANSITIONS


class TestShipmentStateMachineValidTransitions:
    """All valid transitions must succeed without raising."""

    @pytest.mark.parametrize("from_status, to_status", [
        (Shipment.Status.CREATED, Shipment.Status.DISPATCHED),
        (Shipment.Status.CREATED, Shipment.Status.RETURNED),
        (Shipment.Status.DISPATCHED, Shipment.Status.IN_TRANSIT),
        (Shipment.Status.DISPATCHED, Shipment.Status.RETURNED),
        (Shipment.Status.IN_TRANSIT, Shipment.Status.CUSTOMS),
        (Shipment.Status.IN_TRANSIT, Shipment.Status.RETURNED),
        (Shipment.Status.CUSTOMS, Shipment.Status.CLEARED),
        (Shipment.Status.CUSTOMS, Shipment.Status.RETURNED),
        (Shipment.Status.CLEARED, Shipment.Status.OUT_FOR_DELIVERY),
        (Shipment.Status.OUT_FOR_DELIVERY, Shipment.Status.DELIVERED),
        (Shipment.Status.OUT_FOR_DELIVERY, Shipment.Status.FAILED_DELIVERY),
        (Shipment.Status.FAILED_DELIVERY, Shipment.Status.OUT_FOR_DELIVERY),
        (Shipment.Status.FAILED_DELIVERY, Shipment.Status.RETURNED),
    ])
    def test_valid_transition(self, from_status: str, to_status: str, db):
        """Each valid transition passes validation without raising."""
        shipment = Shipment.__new__(Shipment)
        shipment.pk = 1
        shipment.status = from_status
        shipment.carrier_tracking_number = "TRACK123"

        machine = ShipmentStateMachine(shipment)
        # Should not raise
        machine.validate_transition(to_status)


class TestShipmentStateMachineInvalidTransitions:
    """All invalid transitions must raise InvalidShipmentTransitionError."""

    @pytest.mark.parametrize("from_status, to_status", [
        # Skip states
        (Shipment.Status.CREATED, Shipment.Status.DELIVERED),
        (Shipment.Status.CREATED, Shipment.Status.IN_TRANSIT),
        (Shipment.Status.DISPATCHED, Shipment.Status.DELIVERED),
        (Shipment.Status.DISPATCHED, Shipment.Status.CUSTOMS),
        (Shipment.Status.IN_TRANSIT, Shipment.Status.DELIVERED),
        (Shipment.Status.IN_TRANSIT, Shipment.Status.OUT_FOR_DELIVERY),
        # Terminal states — no transitions allowed
        (Shipment.Status.DELIVERED, Shipment.Status.RETURNED),
        (Shipment.Status.DELIVERED, Shipment.Status.IN_TRANSIT),
        (Shipment.Status.RETURNED, Shipment.Status.DISPATCHED),
        (Shipment.Status.RETURNED, Shipment.Status.DELIVERED),
        # Backwards transitions
        (Shipment.Status.CLEARED, Shipment.Status.IN_TRANSIT),
        (Shipment.Status.OUT_FOR_DELIVERY, Shipment.Status.CUSTOMS),
    ])
    def test_invalid_transition_raises(self, from_status: str, to_status: str, db):
        """Each invalid transition must raise InvalidShipmentTransitionError."""
        shipment = Shipment.__new__(Shipment)
        shipment.pk = 1
        shipment.status = from_status

        machine = ShipmentStateMachine(shipment)
        with pytest.raises(InvalidShipmentTransitionError):
            machine.validate_transition(to_status)

    def test_delivered_is_terminal(self):
        """DELIVERED must have no outgoing transitions."""
        allowed = ShipmentStateMachine.get_allowed_transitions(Shipment.Status.DELIVERED)
        assert allowed == set(), f"DELIVERED should be terminal but has transitions: {allowed}"

    def test_returned_is_terminal(self):
        """RETURNED must have no outgoing transitions."""
        allowed = ShipmentStateMachine.get_allowed_transitions(Shipment.Status.RETURNED)
        assert allowed == set(), f"RETURNED should be terminal but has transitions: {allowed}"

    def test_is_terminal_method(self):
        """is_terminal() returns True for terminal states."""
        for terminal in [Shipment.Status.DELIVERED, Shipment.Status.RETURNED]:
            shipment = Shipment.__new__(Shipment)
            shipment.status = terminal
            assert ShipmentStateMachine(shipment).is_terminal() is True

        for non_terminal in [Shipment.Status.CREATED, Shipment.Status.IN_TRANSIT]:
            shipment = Shipment.__new__(Shipment)
            shipment.status = non_terminal
            assert ShipmentStateMachine(shipment).is_terminal() is False
