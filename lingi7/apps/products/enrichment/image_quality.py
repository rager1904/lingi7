"""
Image quality heuristics using Pillow only (no GPU required).

Scores resolution, sharpness (edge energy), and aspect ratio suitability.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageStat, ImageFilter

if TYPE_CHECKING:
    from apps.products.models import Product, ProductImage

logger = logging.getLogger(__name__)

MIN_RECOMMENDED_PIXELS = 800 * 800
MIN_WIDTH = 400
MIN_HEIGHT = 400


def _score_resolution(width: int, height: int) -> float:
    pixels = width * height
    return round(min(1.0, pixels / MIN_RECOMMENDED_PIXELS), 3)


def _score_sharpness(gray: Image.Image) -> float:
    """Edge-energy proxy — higher mean on FIND_EDGES filter ≈ sharper."""
    edges = gray.filter(ImageFilter.FIND_EDGES)
    mean_edge = ImageStat.Stat(edges).mean[0]
    return round(min(1.0, mean_edge / 25.0), 3)


def _score_aspect(width: int, height: int) -> float:
    if height == 0:
        return 0.0
    ratio = width / height
    if 0.75 <= ratio <= 1.33:
        return 1.0
    if 0.5 <= ratio <= 2.0:
        return 0.7
    return 0.4


def score_image_file(path: str | Path) -> dict[str, Any]:
    """Score a single image file on disk."""
    issues: list[str] = []
    path = Path(path)
    try:
        with Image.open(path) as img:
            width, height = img.size
            gray = img.convert("L")
            resolution = _score_resolution(width, height)
            sharpness = _score_sharpness(gray)
            aspect = _score_aspect(width, height)

            if width < MIN_WIDTH or height < MIN_HEIGHT:
                issues.append("resolution_too_low")
            if sharpness < 0.25:
                issues.append("possibly_blurry")
            if aspect < 0.7:
                issues.append("unusual_aspect_ratio")

            overall = round((resolution * 0.4 + sharpness * 0.4 + aspect * 0.2), 3)
            return {
                "width": width,
                "height": height,
                "resolution_score": resolution,
                "sharpness_score": sharpness,
                "aspect_score": aspect,
                "overall_score": overall,
                "issues": issues,
            }
    except OSError as exc:
        logger.warning("Could not score image %s: %s", path, exc)
        return {
            "width": 0,
            "height": 0,
            "resolution_score": 0.0,
            "sharpness_score": 0.0,
            "aspect_score": 0.0,
            "overall_score": 0.0,
            "issues": ["unreadable"],
        }


def score_product_image(product_image: ProductImage) -> dict[str, Any]:
    """Score a ProductImage model instance."""
    if not product_image.image:
        return {"image_id": product_image.pk, "overall_score": 0.0, "issues": ["missing_file"]}
    try:
        path = product_image.image.path
    except (NotImplementedError, ValueError):
        # Remote storage without local path — skip file-based scoring
        return {
            "image_id": product_image.pk,
            "overall_score": 0.5,
            "issues": ["remote_storage"],
        }
    result = score_image_file(path)
    result["image_id"] = product_image.pk
    result["position"] = product_image.position
    return result


def score_product_images(product: Product) -> dict[str, Any]:
    """Score all images for a product and return an aggregate report."""
    images = list(product.images.order_by("position"))
    if not images:
        return {
            "overall": 0.0,
            "image_count": 0,
            "images": [],
            "recommendations": ["Add at least one product photo."],
        }

    scored = [score_product_image(img) for img in images]
    scores = [s.get("overall_score", 0.0) for s in scored]
    overall = round(sum(scores) / len(scores), 3) if scores else 0.0

    recommendations: list[str] = []
    if overall < 0.5:
        recommendations.append("Consider retaking photos with better lighting.")
    if any("resolution_too_low" in s.get("issues", []) for s in scored):
        recommendations.append("Use images at least 800×800 pixels.")
    if any("possibly_blurry" in s.get("issues", []) for s in scored):
        recommendations.append("Some images may be blurry — use a steady hand or tripod.")

    return {
        "overall": overall,
        "image_count": len(scored),
        "images": scored,
        "recommendations": recommendations,
    }
