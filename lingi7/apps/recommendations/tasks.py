"""
apps/recommendations/tasks.py
==============================
Celery tasks for the recommendation engine.

Runs periodically to:
1. Rebuild user preference profiles
2. Refresh cached recommendations for active users
3. Update trending product rankings
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.db.models import Count
from django.utils import timezone

from apps.orders.models import OrderLine
from apps.products.models import Product, Store

from .models import ProductLike, ProductRecommendation, ProductView, UserPreference
from .services import _build_preferences, _compute_hybrid, _save_cache

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def rebuild_user_preferences(self, user_id: int = None):
    """
    Rebuild preference profiles.

    If user_id is provided, rebuild for that single user.
    Otherwise, rebuild for all users with recent activity (last 30 days).
    """
    if user_id:
        from apps.users.models import User
        try:
            user = User.objects.get(pk=user_id)
            _build_preferences(user)
            logger.info("Rebuilt preferences for user %s", user_id)
        except Exception as exc:
            logger.error("Failed to rebuild preferences for user %s: %s", user_id, exc)
            raise self.retry(exc=exc)
        return

    # Bulk rebuild — users active in last 30 days
    cutoff = timezone.now() - timezone.timedelta(days=30)
    active_user_ids = set()

    active_user_ids.update(
        ProductLike.objects.filter(created_at__gte=cutoff)
        .values_list("user_id", flat=True)
    )
    active_user_ids.update(
        ProductView.objects.filter(last_viewed_at__gte=cutoff)
        .values_list("user_id", flat=True)
    )
    active_user_ids.update(
        OrderLine.objects.filter(order__created_at__gte=cutoff)
        .values_list("order__buyer_id", flat=True)
    )

    from apps.users.models import User
    users = User.objects.filter(pk__in=active_user_ids, is_active=True)

    rebuilt = 0
    for user in users:
        try:
            _build_preferences(user)
            rebuilt += 1
        except Exception as exc:
            logger.warning("Failed to rebuild preferences for user %s: %s", user.pk, exc)

    logger.info("Rebuilt preferences for %d active users", rebuilt)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def refresh_recommendations(self, user_id: int = None):
    """
    Refresh cached recommendations.

    If user_id is provided, refresh for that single user.
    Otherwise, refresh for all users with a UserPreference record.
    """
    if user_id:
        from apps.users.models import User
        try:
            user = User.objects.get(pk=user_id)
            recs = _compute_hybrid(user, limit=50)
            _save_cache(user, recs, ProductRecommendation.Strategy.HYBRID)
            logger.info("Refreshed recommendations for user %s", user_id)
        except Exception as exc:
            logger.error("Failed to refresh recommendations for user %s: %s", user_id, exc)
            raise self.retry(exc=exc)
        return

    # Bulk refresh
    prefs = UserPreference.objects.select_related("user").order_by("-computed_at")[:500]
    refreshed = 0

    for pref in prefs:
        try:
            recs = _compute_hybrid(pref.user, limit=50)
            _save_cache(pref.user, recs, ProductRecommendation.Strategy.HYBRID)
            refreshed += 1
        except Exception as exc:
            logger.warning("Failed to refresh recs for user %s: %s", pref.user_id, exc)

    logger.info("Refreshed recommendations for %d users", refreshed)


@shared_task(bind=True, max_retries=1)
def compute_trending_products(self):
    """
    Pre-compute trending products and cache as a platform-wide
    recommendation (stored against a sentinel user_id=None concept).

    This task is designed to be triggered by celery-beat every 6 hours.
    """
    from .services import get_trending_products

    trending = get_trending_products(limit=50)
    product_ids = [p.pk for p in trending]

    logger.info("Computed %d trending products", len(product_ids))
    # Trending is computed on-demand via get_trending_products()
    # This task ensures the data is warm in the DB cache.
    return {"trending_count": len(product_ids), "product_ids": product_ids}
