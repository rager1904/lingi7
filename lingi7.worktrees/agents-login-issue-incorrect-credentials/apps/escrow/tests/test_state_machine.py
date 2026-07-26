"""
apps/escrow/tests/test_state_machine.py

Exhaustive tests for EscrowStateMachine.
Every valid transition is asserted. Every invalid transition is asserted
to raise InvalidTransitionError. No DB access in this module.
"""
from __future__ import annotations

import pytest

from apps.escrow.exceptions import InvalidTransitionError
from apps.escrow.state_machine import EscrowState, EscrowStateMachine

# ---------------------------------------------------------------------------
# Valid transitions — should NOT raise
# ---------------------------------------------------------------------------

VALID_TRANSITIONS = [
    (EscrowState.PENDING, EscrowState.HELD),
    (EscrowState.PENDING, EscrowState.FROZEN),
    (EscrowState.HELD, EscrowState.IN_TRANSIT),
    (EscrowState.HELD, EscrowState.DISPUTED),
    (EscrowState.HELD, EscrowState.FROZEN),
    (EscrowState.HELD, EscrowState.REFUNDED),
    (EscrowState.IN_TRANSIT, EscrowState.DELIVERED),
    (EscrowState.IN_TRANSIT, EscrowState.DISPUTED),
    (EscrowState.IN_TRANSIT, EscrowState.FROZEN),
    (EscrowState.DELIVERED, EscrowState.RELEASED),
    (EscrowState.DELIVERED, EscrowState.DISPUTED),
    (EscrowState.DELIVERED, EscrowState.FROZEN),
    (EscrowState.DISPUTED, EscrowState.RELEASED),
    (EscrowState.DISPUTED, EscrowState.REFUNDED),
    (EscrowState.DISPUTED, EscrowState.FROZEN),
    (EscrowState.FROZEN, EscrowState.RELEASED),
    (EscrowState.FROZEN, EscrowState.REFUNDED),
    (EscrowState.FROZEN, EscrowState.DISPUTED),
]

# ---------------------------------------------------------------------------
# Invalid transitions — must raise InvalidTransitionError
# ---------------------------------------------------------------------------

INVALID_TRANSITIONS = [
    # Terminal states block everything
    (EscrowState.RELEASED, EscrowState.PENDING),
    (EscrowState.RELEASED, EscrowState.HELD),
    (EscrowState.RELEASED, EscrowState.FROZEN),
    (EscrowState.RELEASED, EscrowState.REFUNDED),
    (EscrowState.RELEASED, EscrowState.DISPUTED),
    (EscrowState.RELEASED, EscrowState.RELEASED),
    (EscrowState.REFUNDED, EscrowState.PENDING),
    (EscrowState.REFUNDED, EscrowState.HELD),
    (EscrowState.REFUNDED, EscrowState.RELEASED),
    # Can't skip states
    (EscrowState.PENDING, EscrowState.RELEASED),
    (EscrowState.PENDING, EscrowState.DELIVERED),
    (EscrowState.PENDING, EscrowState.IN_TRANSIT),
    (EscrowState.PENDING, EscrowState.DISPUTED),
    (EscrowState.PENDING, EscrowState.REFUNDED),
    (EscrowState.HELD, EscrowState.RELEASED),
    (EscrowState.HELD, EscrowState.DELIVERED),
    (EscrowState.IN_TRANSIT, EscrowState.RELEASED),
    (EscrowState.IN_TRANSIT, EscrowState.HELD),
    # Can't go backwards
    (EscrowState.DELIVERED, EscrowState.PENDING),
    (EscrowState.DELIVERED, EscrowState.HELD),
    (EscrowState.DELIVERED, EscrowState.IN_TRANSIT),
    (EscrowState.FROZEN, EscrowState.PENDING),
    (EscrowState.FROZEN, EscrowState.HELD),
    (EscrowState.FROZEN, EscrowState.IN_TRANSIT),
    (EscrowState.FROZEN, EscrowState.DELIVERED),
]


@pytest.mark.parametrize("current,target", VALID_TRANSITIONS)
def test_valid_transitions_do_not_raise(current: str, target: str) -> None:
    """All valid transitions should pass without raising."""
    EscrowStateMachine.validate(current, target)  # no exception = pass


@pytest.mark.parametrize("current,target", INVALID_TRANSITIONS)
def test_invalid_transitions_raise(current: str, target: str) -> None:
    """All invalid transitions must raise InvalidTransitionError."""
    with pytest.raises(InvalidTransitionError) as exc_info:
        EscrowStateMachine.validate(current, target)
    assert exc_info.value.current_state == current
    assert exc_info.value.attempted_state == target


def test_invalid_state_raises_value_error() -> None:
    """Unknown state string should raise ValueError, not InvalidTransitionError."""
    with pytest.raises(ValueError, match="Unknown"):
        EscrowStateMachine.validate("NOT_A_STATE", EscrowState.HELD)


def test_invalid_target_state_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown target"):
        EscrowStateMachine.validate(EscrowState.HELD, "NONSENSE")


def test_terminal_states_are_correct() -> None:
    assert EscrowState.RELEASED in EscrowState.TERMINAL
    assert EscrowState.REFUNDED in EscrowState.TERMINAL
    assert EscrowState.HELD not in EscrowState.TERMINAL
    assert EscrowState.FROZEN not in EscrowState.TERMINAL


def test_is_terminal_released() -> None:
    assert EscrowStateMachine.is_terminal(EscrowState.RELEASED) is True


def test_is_terminal_refunded() -> None:
    assert EscrowStateMachine.is_terminal(EscrowState.REFUNDED) is True


def test_is_terminal_held() -> None:
    assert EscrowStateMachine.is_terminal(EscrowState.HELD) is False


def test_valid_next_states_pending() -> None:
    nexts = EscrowStateMachine.valid_next_states(EscrowState.PENDING)
    assert EscrowState.HELD in nexts
    assert EscrowState.FROZEN in nexts
    assert EscrowState.RELEASED not in nexts


def test_valid_next_states_terminal_is_empty() -> None:
    for terminal in EscrowState.TERMINAL:
        assert EscrowStateMachine.valid_next_states(terminal) == frozenset()


def test_all_states_have_transition_entries() -> None:
    """Ensure no state is missing from the transition map."""
    from apps.escrow.state_machine import _TRANSITIONS
    for state in EscrowState.ALL:
        assert state in _TRANSITIONS, f"State '{state}' missing from transition map"


def test_invalid_current_state_in_valid_next_states() -> None:
    with pytest.raises(ValueError, match="Unknown"):
        EscrowStateMachine.valid_next_states("GHOST_STATE")
