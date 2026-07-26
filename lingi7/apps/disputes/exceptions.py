"""
Dispute domain exceptions — apps/disputes/exceptions.py
"""


class DisputeError(Exception):
    """Base exception for all dispute domain errors."""


class InvalidDisputeTransitionError(DisputeError):
    """Raised when an invalid status transition is attempted."""


class DisputeAlreadyExistsError(DisputeError):
    """Raised when a dispute is opened on an order that already has one."""


class EvidenceSubmissionClosedError(DisputeError):
    """Raised when evidence is submitted after the dispute is resolved/withdrawn."""


class DisputeNotOpenError(DisputeError):
    """Raised when an action requires the dispute to be open/under-review."""
