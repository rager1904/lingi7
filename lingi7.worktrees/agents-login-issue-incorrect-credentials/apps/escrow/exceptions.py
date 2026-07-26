"""
apps/escrow/exceptions.py

Custom exception hierarchy for the Lingi7 escrow system.
All escrow-related errors derive from EscrowError so callers
can catch broadly or narrowly as needed.
"""


class EscrowError(Exception):
    """Base exception for all escrow-related errors."""


class InvalidTransitionError(EscrowError):
    """
    Raised when a state transition is attempted that is not permitted
    by the EscrowStateMachine transition map.

    Attributes:
        current_state: The state the account was in when the error occurred.
        attempted_state: The state that was attempted.
    """

    def __init__(self, current_state: str, attempted_state: str) -> None:
        self.current_state = current_state
        self.attempted_state = attempted_state
        super().__init__(
            f"Cannot transition escrow from '{current_state}' to '{attempted_state}'."
        )


class FraudGateError(EscrowError):
    """
    Raised when the fraud gate blocks an escrow RELEASED transition.
    The account will have been moved to FROZEN state before this is raised.
    """


class LedgerImbalanceError(EscrowError):
    """
    Raised when a double-entry integrity check fails — i.e., the sum
    of DEBIT entries does not equal the sum of CREDIT entries for a
    given operation.
    """


class InsufficientBalanceError(EscrowError):
    """
    Raised when a fund movement would result in a negative escrow balance.
    """


class EscrowAlreadyExistsError(EscrowError):
    """
    Raised when attempting to create an EscrowAccount for an Order that
    already has one.
    """


class ReconciliationError(EscrowError):
    """
    Raised by the reconciliation task when a balance discrepancy is detected.
    This is a critical alert — it must trigger immediate human review.
    """
