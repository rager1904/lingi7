"""
apps/products/permissions.py
============================
Custom DRF permission classes for multi-tenant vendor isolation.

IsVendor            — User must have role=VENDOR
IsStoreApproved     — Vendor must have an APPROVED store
IsStoreOwner        — Object-level: vendor may only touch their own store's data
IsAdminOrReadOnly   — Admin has full access; others are read-only
"""

from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.views import View

from apps.products.models import Store


class IsVendor(BasePermission):
    """Require the authenticated user to have role=VENDOR."""

    message = "Only vendor accounts may access this resource."

    def has_permission(self, request: Request, view: View) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "VENDOR"
        )


class IsStoreApproved(BasePermission):
    """
    Require the vendor to have a store in APPROVED status.

    Returns 403 for PENDING / REJECTED / SUSPENDED stores with an
    informative message so vendors understand the gating.
    """

    message = "Your store has not been approved yet. Please wait for admin review."

    def has_permission(self, request: Request, view: View) -> bool:
        try:
            return request.user.store.is_active
        except (AttributeError, Store.DoesNotExist):
            return False


class IsStoreOwner(BasePermission):
    """
    Object-level permission — vendor may only modify their own store's objects.

    Applied on Product, ProductImage, and Order detail views.
    Requires the object to have a `store` FK attribute.
    """

    message = "You may only access resources belonging to your own store."

    def has_object_permission(self, request: Request, view: View, obj: object) -> bool:
        store = getattr(obj, "store", None)
        if store is None:
            return False
        return store.owner == request.user


class IsAdminOrReadOnly(BasePermission):
    """
    Admin users have full CRUD access.
    All other authenticated users are read-only on safe methods.
    Anonymous users are denied entirely.
    """

    def has_permission(self, request: Request, view: View) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_staff
