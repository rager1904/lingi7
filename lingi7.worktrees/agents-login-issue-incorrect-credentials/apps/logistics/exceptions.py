"""
Logistics domain exceptions for Lingi7.

Reference: LG7-BE-009 | apps/logistics/exceptions.py
"""


class LogisticsError(Exception):
    """Base exception for logistics domain errors."""


class InvalidShipmentTransitionError(LogisticsError):
    """Raised when a status transition is not permitted by the state machine."""


class ShipmentAlreadyExistsError(LogisticsError):
    """Raised when attempting to create a second shipment for the same order."""


class CarrierAPIError(LogisticsError):
    """Raised when a carrier API call fails after retries."""


class TrackingNumberRequiredError(LogisticsError):
    """Raised when a carrier tracking number is required but not provided."""


class DeliveryAlreadyConfirmedError(LogisticsError):
    """Raised when attempting to deliver an already-delivered shipment."""
