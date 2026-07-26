"""
3D asset generation extension point.

Local mesh pipelines can be wired here without requiring hosted model services.
Implement generate_3d_preview(product) when a CPU-friendly 3D stack is available.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.products.models import Product


def generate_3d_preview(product: Product) -> dict[str, Any] | None:
    """Stub — returns None until a 3D pipeline is integrated."""
    return None
