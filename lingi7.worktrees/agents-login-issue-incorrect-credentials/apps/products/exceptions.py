"""
apps/products/exceptions.py
===========================
Domain-specific exceptions for the products module.

All exceptions inherit from a base ProductError so callers can catch
the entire domain with a single except clause where needed.
"""


class ProductError(Exception):
    """Base exception for the products domain."""


class StoreError(ProductError):
    """Raised for invalid store operations (duplicate registration, etc.)."""


class InvalidStoreTransitionError(StoreError):
    """Raised when a Store status transition is not permitted."""


class InvalidProductTransitionError(ProductError):
    """Raised when a Product status transition is not permitted."""


class InventoryError(ProductError):
    """Raised when an inventory operation cannot be completed."""


class InsufficientStockError(InventoryError):
    """Raised when available stock is insufficient for an operation."""
