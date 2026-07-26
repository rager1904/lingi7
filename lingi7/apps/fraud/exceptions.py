"""apps/fraud/exceptions.py — Fraud domain exceptions."""


class FraudGateError(Exception):
    """
    Raised by EscrowService when FraudPipeline returns should_freeze=True.

    Must be raised AFTER the escrow state has been transitioned to FROZEN
    inside an independent atomic block. Raising inside the outer atomic
    block causes a rollback of the state transition.
    """


class FraudConfigurationError(Exception):
    """Raised when fraud system configuration is invalid or missing."""
