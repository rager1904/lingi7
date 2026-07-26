"""
apps/escrow/state_machine.py

Pure-logic escrow state machine for the Lingi7 platform.
This module contains NO database access — it is a stateless validator.
All persistence is handled by EscrowService (services.py).

States
------
PENDING     → Payment initiated, not yet confirmed by provider webhook.
HELD        → Payment confirmed. Funds locked. Seller notified to fulfil.
IN_TRANSIT  → Seller has marked order shipped. Tracking number provided.
DELIVERED   → Buyer confirmed delivery OR 7-day auto-confirm expired.
RELEASED    → Fraud gate passed. Funds disbursed to vendor payout account.
DISPUTED    → Buyer raised a dispute before the auto-confirm window closed.
REFUNDED    → Dispute resolved in buyer's favour OR seller SLA breach.
FROZEN      → Fraud engine flagged high risk (score >= 0.65). Manual review required.
"""
from __future__ import annotations

from typing import FrozenSet


class EscrowState:
    """String constants for all valid escrow states."""

    PENDING = "PENDING"
    HELD = "HELD"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    RELEASED = "RELEASED"
    DISPUTED = "DISPUTED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    REFUNDED = "REFUNDED"
    FROZEN = "FROZEN"

    ALL: FrozenSet[str] = frozenset(
        {PENDING, HELD, IN_TRANSIT, DELIVERED, RELEASED, DISPUTED, PARTIALLY_REFUNDED, REFUNDED, FROZEN}
    )

    # Terminal states — no further transitions are permitted
    TERMINAL: FrozenSet[str] = frozenset({RELEASED, REFUNDED})


# Adjacency map: state → set of valid next states
_TRANSITIONS: dict[str, FrozenSet[str]] = {
    EscrowState.PENDING: frozenset({EscrowState.HELD, EscrowState.FROZEN}),
    EscrowState.HELD: frozenset(
        {EscrowState.IN_TRANSIT, EscrowState.DISPUTED, EscrowState.FROZEN, EscrowState.REFUNDED, EscrowState.PARTIALLY_REFUNDED}
    ),
    EscrowState.IN_TRANSIT: frozenset(
        {EscrowState.DELIVERED, EscrowState.DISPUTED, EscrowState.FROZEN}
    ),
    EscrowState.DELIVERED: frozenset(
        {EscrowState.RELEASED, EscrowState.DISPUTED, EscrowState.FROZEN}
    ),
    EscrowState.RELEASED: frozenset(),  # terminal
    EscrowState.DISPUTED: frozenset(
        {EscrowState.RELEASED, EscrowState.REFUNDED, EscrowState.PARTIALLY_REFUNDED, EscrowState.FROZEN}
    ),
    EscrowState.PARTIALLY_REFUNDED: frozenset(
        {EscrowState.RELEASED, EscrowState.REFUNDED, EscrowState.DISPUTED, EscrowState.FROZEN}
    ),
    EscrowState.REFUNDED: frozenset(),  # terminal
    EscrowState.FROZEN: frozenset(
        {EscrowState.RELEASED, EscrowState.REFUNDED, EscrowState.DISPUTED, EscrowState.PARTIALLY_REFUNDED}
    ),
}


class EscrowStateMachine:
    """
    Validates escrow state transitions without touching the database.

    Usage:
        EscrowStateMachine.validate(current_state, target_state)
        # Raises InvalidTransitionError if the transition is not allowed.

        EscrowStateMachine.valid_next_states(current_state)
        # Returns the set of states reachable from current_state.
    """

    @staticmethod
    def valid_next_states(current_state: str) -> FrozenSet[str]:
        """
        Return the set of states that are reachable from *current_state*.

        Args:
            current_state: A value from EscrowState.

        Returns:
            FrozenSet of valid target state strings.

        Raises:
            ValueError: If current_state is not a recognised escrow state.
        """
        if current_state not in EscrowState.ALL:
            raise ValueError(f"Unknown escrow state: '{current_state}'")
        return _TRANSITIONS[current_state]

    @staticmethod
    def validate(current_state: str, target_state: str) -> None:
        """
        Assert that transitioning from *current_state* to *target_state*
        is permitted.

        Args:
            current_state: The current state of the EscrowAccount.
            target_state: The desired next state.

        Raises:
            ValueError: If either state is not a recognised escrow state.
            InvalidTransitionError: If the transition is not in the map.
        """
        from apps.escrow.exceptions import InvalidTransitionError  # local import to avoid circulars

        if current_state not in EscrowState.ALL:
            raise ValueError(f"Unknown current state: '{current_state}'")
        if target_state not in EscrowState.ALL:
            raise ValueError(f"Unknown target state: '{target_state}'")

        if target_state not in _TRANSITIONS[current_state]:
            raise InvalidTransitionError(current_state, target_state)

    @staticmethod
    def is_terminal(state: str) -> bool:
        """Return True if *state* is a terminal state (no further transitions)."""
        return state in EscrowState.TERMINAL
