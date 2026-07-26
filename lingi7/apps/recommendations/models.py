"""
apps/recommendations/models.py
==============================
Per-user recommendation data models for Lingi7.

Tracks:
    - ProductLike — heart / favourite toggle
    - ProductView — browsing history (deduplicated per user+product)
    - ProductRating — 1-5 star rating with optional review
    - Wishlist — named save-for-later lists
    - UserPreference — materialised user taste profile (category + tag weights)
    - ProductRecommendation — cached per-user recommendation snapshots

All models use composite unique constraints to prevent duplicate engagement
and support efficient queryset patterns for the recommendation engine.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


# ---------------------------------------------------------------------------
# ProductLike
# ---------------------------------------------------------------------------

class ProductLike(models.Model):
    """
    Heart / favourite toggle.  One row per user+product pair.
    Created on like, deleted on unlike (toggle semantics).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_likes",
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="likes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "product")
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["product", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} likes {self.product}"


# ---------------------------------------------------------------------------
# ProductView
# ---------------------------------------------------------------------------

class ProductView(models.Model):
    """
    Browsing history — one row per user+product pair, updated on each view.
    The ``view_count`` increments on revisit and ``last_viewed_at`` tracks
    recency for the time-decay weighting in the recommendation engine.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_views",
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="viewer_records",
    )
    view_count = models.PositiveIntegerField(default=1)
    first_viewed_at = models.DateTimeField(auto_now_add=True)
    last_viewed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "product")
        indexes = [
            models.Index(fields=["user", "last_viewed_at"]),
            models.Index(fields=["product", "last_viewed_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} viewed {self.product} x{self.view_count}"


# ---------------------------------------------------------------------------
# ProductRating
# ---------------------------------------------------------------------------

class ProductRating(models.Model):
    """
    1-5 star rating with optional text review.  One rating per user+product.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_ratings",
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="ratings",
    )
    score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    review = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "product")
        indexes = [
            models.Index(fields=["product", "score"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} rated {self.product}: {self.score}/5"


# ---------------------------------------------------------------------------
# Wishlist
# ---------------------------------------------------------------------------

class Wishlist(models.Model):
    """
    Named save-for-later list.  Users can have multiple wishlists
    (e.g. "Birthday Ideas", "Tech Upgrades").  Each item is a unique
    user + wishlist + product triple.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlists",
    )
    name = models.CharField(max_length=120, default="My Wishlist")
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="wishlist_entries",
    )
    note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "name", "product")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "name"]),
        ]

    def __str__(self) -> str:
        return f"{self.name}: {self.product}"


# ---------------------------------------------------------------------------
# UserPreference  (materialised taste profile)
# ---------------------------------------------------------------------------

class UserPreference(models.Model):
    """
    Materialised user taste profile — rebuilt periodically by Celery task.
    Stores aggregate weights for categories, tags, and price ranges so the
    recommendation engine can do fast lookups without scanning raw events.

    ``category_weights``:  {"electronics": 0.45, "fashion": 0.30, ...}
    ``tag_weights``:       {"wireless": 0.32, "nike": 0.18, ...}
    ``price_range``:       {"min": 50, "max": 500, "avg": 220, "median": 180}
    ``engagement_score``:  total likes + 2*buys + 0.5*views (for popularity)
    ``top_products``:      [product_id, ...] — most engaged product IDs
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preference",
    )
    category_weights = models.JSONField(default=dict, blank=True)
    tag_weights = models.JSONField(default=dict, blank=True)
    price_range = models.JSONField(default=dict, blank=True)
    engagement_score = models.FloatField(default=0.0)
    top_products = models.JSONField(default=list, blank=True)
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["-engagement_score"]),
        ]

    def __str__(self) -> str:
        return f"Preferences for {self.user}"


# ---------------------------------------------------------------------------
# ProductRecommendation  (cached results)
# ---------------------------------------------------------------------------

class ProductRecommendation(models.Model):
    """
    Cached per-user recommendation snapshot.
    Rebuilt periodically or on-demand.  Each row links a user to a
    recommended product with a confidence score and the strategy
    that produced it.
    """

    class Strategy(models.TextChoices):
        COLLABORATIVE = "collaborative", "Collaborative Filtering"
        CONTENT_BASED = "content_based", "Content-Based"
        POPULARITY = "popularity", "Popularity/Trending"
        HYBRID = "hybrid", "Hybrid Ensemble"
        PURCHASE_HISTORY = "purchase_history", "Purchase History"
        SIMILAR_USERS = "similar_users", "Similar Users Also Liked"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cached_recommendations",
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="recommended_for",
    )
    score = models.FloatField(default=0.0)
    strategy = models.CharField(
        max_length=20,
        choices=Strategy.choices,
        default=Strategy.HYBRID,
    )
    position = models.PositiveSmallIntegerField(default=0)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "product", "strategy")
        ordering = ["user", "-score", "position"]
        indexes = [
            models.Index(fields=["user", "strategy", "-score"]),
            models.Index(fields=["product", "strategy"]),
        ]

    def __str__(self) -> str:
        return f"Recommendation: {self.product} for {self.user} ({self.strategy})"
