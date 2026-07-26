"""
Shipment state machine for Lingi7.

Defines valid status transitions and enforces guard clauses.
No transition may occur outside this machine.

Reference: LG7-BE-009 | apps/logistics/state_machine.py
"""

from __future__ import annotations

from apps.logistics.models import Shipment
from apps.logistics.exceptions import InvalidShipmentTransitionError


# Valid transitions: {from_status: {allowed_to_statuses}}
VALID_TRANSITIONS: dict[str, set[str]] = {
    Shipment.Status.CREATED: {
        Shipment.Status.DISPATCHED,
        Shipment.Status.RETURNED,  # cancelled before dispatch
    },
    Shipment.Status.DISPATCHED: {
        Shipment.Status.IN_TRANSIT,
        Shipment.Status.RETURNED,
    },
    Shipment.Status.IN_TRANSIT: {
        Shipment.Status.CUSTOMS,
        Shipment.Status.RETURNED,
    },
    Shipment.Status.CUSTOMS: {
        Shipment.Status.CLEARED,
        Shipment.Status.RETURNED,  # customs seizure / rejection
    },
    Shipment.Status.CLEARED: {
        Shipment.Status.OUT_FOR_DELIVERY,
    },
    Shipment.Status.OUT_FOR_DELIVERY: {
        Shipment.Status.DELIVERED,
        Shipment.Status.FAILED_DELIVERY,
    },
    Shipment.Status.DELIVERED: set(),  # Terminal — no further transitions
    Shipment.Status.FAILED_DELIVERY: {
        Shipment.Status.OUT_FOR_DELIVERY,  # Re-attempt delivery
        Shipment.Status.RETURNED,
    },
    Shipment.Status.RETURNED: set(),  # Terminal
}

# Statuses that require a carrier tracking number before transition
TRACKING_REQUIRED_STATUSES: set[str] = {
    Shipment.Status.DISPATCHED,
    Shipment.Status.IN_TRANSIT,
    Shipment.Status.OUT_FOR_DELIVERY,
    Shipment.Status.DELIVERED,
}


class ShipmentStateMachine:
    """
    Enforces valid Shipment status transitions.

    Usage:
        machine = ShipmentStateMachine(shipment)
        machine.validate_transition(Shipment.Status.IN_TRANSIT)
        # raises InvalidShipmentTransitionError if not allowed
    """

    def __init__(self, shipment: Shipment) -> None:
        self.shipment = shipment

    def validate_transition(self, to_status: str) -> None:
        """
        Assert that a transition from current status to to_status is legal.

        Args:
            to_status: Target status value from Shipment.Status.

        Raises:
            InvalidShipmentTransitionError: If the transition is not permitted.
        """
        from_status = self.shipment.status
        allowed = VALID_TRANSITIONS.get(from_status, set())

        if to_status not in allowed:
            raise InvalidShipmentTransitionError(
                f"Cannot transition Shipment #{self.shipment.pk} "
                f"from '{from_status}' to '{to_status}'. "
                f"Allowed: {sorted(allowed) or 'none (terminal state)'}."
            )

    def is_terminal(self) -> bool:
        """True if the current status has no further transitions."""
        return not VALID_TRANSITIONS.get(self.shipment.status, set())

    @staticmethod
    def get_allowed_transitions(from_status: str) -> set[str]:
        """Return the set of statuses reachable from from_status."""
        return VALID_TRANSITIONS.get(from_status, set())
