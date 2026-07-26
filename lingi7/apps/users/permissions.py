"""
apps/users/permissions.py
-------------------------
Custom DRF permission classes for the Lingi7 platform.

Design:
- All permission classes are composable with & and | operators (DRF 3.9+).
- IsKYCVerified is the primary escrow gate — any view that touches funds
  must include this permission.
- IsNotFrozen is a separate concern from IsKYCVerified — a verified user
  can be frozen post-verification by the fraud engine.
- Admin permissions require both is_staff and the ADMIN role — having one
  without the other is treated as a misconfiguration.

Usage example:
    class EscrowReleaseView(APIView):
        permission_classes = [IsAuthenticated, IsKYCVerified, IsNotFrozen, IsBuyer]
"""

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.users.models import KYCStatus, UserRole


class IsBuyer(BasePermission):
    """
    Allow access only to users with the BUYER role.

    Used on: place_order, payment initiation, dispute raise.
    """

    message = "Access restricted to Buyer accounts."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.BUYER
        )


class IsVendor(BasePermission):
    """
    Allow access only to users with the VENDOR role.

    Used on: product create/edit, shipment update, vendor dashboard.
    """

    message = "Access restricted to Vendor accounts."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.VENDOR
        )


class IsAdmin(BasePermission):
    """
    Allow access only to users with the ADMIN role AND is_staff=True.

    Dual check prevents partial misconfiguration from granting admin access.
    Used on: KYC review, account freeze, escrow override, AdminAuditLog.
    """

    message = "Access restricted to platform administrators."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return (
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
            and request.user.role == UserRole.ADMIN
        )


class IsKYCVerified(BasePermission):
    """
    Allow access only to users whose KYC status is VERIFIED.

    This is the primary BoZ KYC compliance gate.
    Must be applied to ALL escrow, payment, and order endpoints.

    A user with PENDING or REJECTED KYC status cannot transact.
    """

    message = (
        "Your identity has not been verified. "
        "Please complete KYC verification before transacting."
    )

    def has_permission(self, request: Request, view: APIView) -> bool:
        return (
            request.user
            and request.user.is_authenticated
            and request.user.kyc_status == KYCStatus.VERIFIED
        )


class IsNotFrozen(BasePermission):
    """
    Deny access if the user's account is frozen.

    Applied in conjunction with IsKYCVerified on all transactional endpoints.
    The fraud engine and admins can freeze a KYC-verified account — this
    permission ensures frozen accounts are blocked at the API layer.
    """

    message = (
        "Your account has been frozen. "
        "Please contact support@lingi7.com for assistance."
    )

    def has_permission(self, request: Request, view: APIView) -> bool:
        return (
            request.user
            and request.user.is_authenticated
            and not request.user.is_frozen
        )


class CanTransact(BasePermission):
    """
    Composite gate: active + KYC verified + not frozen.

    Convenience class that combines the three transactional prerequisites.
    Equivalent to: IsAuthenticated & IsKYCVerified & IsNotFrozen.

    Prefer using this on escrow/payment endpoints for conciseness.
    """

    message = (
        "Transaction not permitted. Your account must be active, "
        "KYC-verified, and not frozen."
    )

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        return (
            user
            and user.is_authenticated
            and user.is_active
            and user.kyc_status == KYCStatus.VERIFIED
            and not user.is_frozen
        )


class IsSelf(BasePermission):
    """
    Object-level permission: user can only access their own resource.

    Used on: /api/users/me/ and any user-specific sub-resource.
    """

    message = "You do not have permission to access this resource."

    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        return request.user and request.user.is_authenticated and obj == request.user
