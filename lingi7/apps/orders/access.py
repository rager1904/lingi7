"""
Order access control helpers — party checks for IDOR prevention.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.exceptions import PermissionDenied

from apps.orders.models import Order

if TYPE_CHECKING:
    from apps.users.models import User


def assert_order_party(
    order: Order,
    actor: "User",
    *,
    allow_buyer: bool = True,
    allow_seller: bool = True,
    allow_staff: bool = True,
) -> None:
    """Raise PermissionDenied unless actor is an allowed party on the order."""
    if allow_staff and actor.is_staff:
        return
    if allow_buyer and actor == order.buyer:
        return
    if allow_seller and actor == order.seller:
        return
    raise PermissionDenied("You do not have permission to act on this order.")
