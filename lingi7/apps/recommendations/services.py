"""
apps/recommendations/services.py
=================================
Hybrid recommendation engine for Lingi7.

Combines five signals into a single scored ranking:

1. **Collaborative filtering** — "users who bought/liked X also bought/liked Y"
2. **Content-based** — category + tag overlap with user's taste profile
3. **Popularity / trending** — weighted engagement (likes, buys, views) with
   time-decay so recent activity counts more
4. **Purchase history** — category affinity from past orders
5. **Price-range affinity** — prefer products in the user's typical spend band

Each signal produces a 0–1 normalised score; the final hybrid score is a
weighted average.  Cold-start users (no history) fall back to popularity.

All public functions accept a ``user`` instance and return a list of
``Product`` objects annotated with ``_rec_score``.
"""

from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import (
    Avg,
    Count,
    F,
    FloatField,
    Q,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.orders.models import Order, OrderLine
from apps.products.models import Category, Product, Store

from .models import (
    ProductLike,
    ProductRating,
    ProductRecommendation,
    ProductView,
    UserPreference,
    Wishlist,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Signal weights for the hybrid ensemble
# ---------------------------------------------------------------------------
WEIGHTS = {
    "collaborative": 0.25,
    "content_based": 0.30,
    "popularity": 0.15,
    "purchase_history": 0.20,
    "price_affinity": 0.10,
}

# Time-decay half-life in days — activity older than this counts half
TIME_DECAY_HALF_LIFE_DAYS = 30

# Maximum number of recommendations to cache per user
MAX_RECS = 50

# Minimum number of engagement events before switching from cold-start
MIN_EVENTS_FOR_PERSONALISATION = 3


# ===================================================================
# Public API
# ===================================================================

def get_recommendations(
    user,
    limit: int = 20,
    strategy: str | None = None,
) -> list[Product]:
    """
    Return the top ``limit`` recommended products for ``user``.

    Strategy can be None (hybrid), or one of the Strategy choices to force
    a single signal.  Results are cached in ProductRecommendation and
    served from cache when fresh (< 1 hour old).
    """
    limit = min(limit, MAX_RECS)

    # Try cache first
    cached = _get_fresh_cache(user, strategy, limit)
    if cached:
        return cached

    # Compute fresh
    recs = _compute_hybrid(user, limit)

    # Persist cache
    _save_cache(user, recs, strategy or ProductRecommendation.Strategy.HYBRID)

    return [r["product"] for r in recs]


def get_similar_products(
    product: Product,
    limit: int = 10,
) -> list[Product]:
    """
    Return products similar to ``product`` using content features
    (category, tags, price band) weighted by engagement popularity.
    """
    qs = (
        _visible_products()
        .exclude(pk=product.pk)
        .select_related("store", "category")
        .prefetch_related("images")
    )

    # Build scoring query
    tag_filter = Q()
    for tag in (product.suggested_tags or [])[:8]:
        tag_filter |= Q(suggested_tags__icontains=tag)

    same_category = Q(category=product.category)
    price_band = _price_band_q(product.price)

    # Annotate with composite similarity score
    qs = qs.annotate(
        _cat_score=Value(1.0, output_field=FloatField()),
        _tag_score=Count(
            "id",  # placeholder — real tag scoring done in Python
            filter=tag_filter,
            output_field=FloatField(),
        ),
        _pop_score=Coalesce(
            Sum("likes__id", distinct=True, output_field=FloatField()),
            Value(0.0, output_field=FloatField()),
        ),
    )

    candidates = list(qs.filter(same_category | tag_filter).order_by("-_pop_score")[:limit * 3])

    # Rank by composite similarity
    scored = []
    for p in candidates:
        score = 0.0
        if p.category_id == product.category_id:
            score += 0.4
        # Tag overlap
        overlap = len(set(product.suggested_tags or []) & set(p.suggested_tags or []))
        score += min(overlap * 0.1, 0.3)
        # Price proximity
        if product.price > 0:
            price_ratio = min(p.price, product.price) / max(p.price, product.price)
            score += price_ratio * 0.2
        # Popularity tie-breaker
        score += min(float(p._pop_score or 0) * 0.01, 0.1)
        scored.append((score, p))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:limit]]


def get_trending_products(limit: int = 20) -> list[Product]:
    """
    Platform-wide trending products based on recent engagement velocity
    (likes + 2×buys + 0.5×views in the last 7 days, time-decayed).
    """
    cutoff = timezone.now() - timedelta(days=7)

    # Recent likes per product
    like_counts = dict(
        ProductLike.objects.filter(created_at__gte=cutoff)
        .values_list("product_id")
        .annotate(c=Count("id"))
        .values_list("product_id", "c")
    )

    # Recent views per product
    view_counts = dict(
        ProductView.objects.filter(last_viewed_at__gte=cutoff)
        .values_list("product_id")
        .annotate(c=Count("id"))
        .values_list("product_id", "c")
    )

    # Recent purchases per product (via OrderLine)
    buy_counts = dict(
        OrderLine.objects.filter(order__created_at__gte=cutoff)
        .values_list("product_id")
        .annotate(c=Count("id"))
        .values_list("product_id", "c")
    )

    # Score all visible products
    product_ids = set(like_counts) | set(view_counts) | set(buy_counts)
    if not product_ids:
        return list(_visible_products().order_by("-created_at")[:limit])

    scores = {}
    for pid in product_ids:
        scores[pid] = (
            like_counts.get(pid, 0)
            + 2 * buy_counts.get(pid, 0)
            + 0.5 * view_counts.get(pid, 0)
        )

    top_ids = sorted(scores, key=scores.get, reverse=True)[:limit * 2]

    products = {
        p.pk: p
        for p in _visible_products().filter(pk__in=top_ids)
    }

    return [products[pid] for pid in top_ids if pid in products][:limit]


def get_similar_users_top_picks(user, limit: int = 20) -> list[Product]:
    """
    Find products that users with similar taste profiles engage with
    but the current user hasn't interacted with yet.
    """
    prefs = _get_or_compute_preferences(user)
    if not prefs or not prefs.get("category_weights"):
        return []

    # Find top categories
    top_cats = sorted(prefs["category_weights"], key=prefs["category_weights"].get, reverse=True)[:5]
    top_tags = sorted(prefs.get("tag_weights", {}), key=prefs.get("tag_weights", {}).get, reverse=True)[:10]

    # Find users with overlapping category interests
    similar_users = (
        UserPreference.objects.filter(
            category_weights__has_any_keys=top_cats,
        )
        .exclude(user=user)
        .order_by("-engagement_score")[:50]
    )

    if not similar_users:
        return []

    similar_user_ids = [up.user_id for up in similar_users]

    # Get products these users engaged with
    engaged_product_ids = set()
    engaged_product_ids.update(
        ProductLike.objects.filter(user_id__in=similar_user_ids).values_list("product_id", flat=True)
    )
    engaged_product_ids.update(
        Wishlist.objects.filter(user_id__in=similar_user_ids).values_list("product_id", flat=True)
    )
    engaged_product_ids.update(
        OrderLine.objects.filter(order__buyer_id__in=similar_user_ids).values_list("product_id", flat=True)
    )

    # Exclude products the current user already engaged with
    user_engaged = _user_engaged_product_ids(user)
    fresh_ids = engaged_product_ids - user_engaged

    if not fresh_ids:
        return []

    return list(
        _visible_products()
        .filter(pk__in=fresh_ids)
        .order_by("-created_at")[:limit]
    )


def get_for_you_feed(user, limit: int = 20) -> list[dict[str, Any]]:
    """
    Rich 'For You' feed that blends multiple recommendation strategies
    with explanations for each recommendation.
    """
    limit = min(limit, MAX_RECS)
    prefs = _get_or_compute_preferences(user)
    is_cold = _is_cold_start(user, prefs)

    sections = []

    if is_cold:
        sections.append({
            "title": "Trending Now",
            "subtitle": "Popular across the marketplace",
            "strategy": "popularity",
            "products": _serialize(_get_trending(limit=limit)),
        })
        sections.append({
            "title": "New Arrivals",
            "subtitle": "Fresh finds just added",
            "strategy": "newest",
            "products": _serialize(
                list(_visible_products().order_by("-created_at")[:limit])
            ),
        })
    else:
        # Personalised sections
        hybrid_recs = get_recommendations(user, limit=limit)
        sections.append({
            "title": "Picked For You",
            "subtitle": "Based on your likes, buys, and browsing",
            "strategy": "hybrid",
            "products": _serialize(hybrid_recs),
        })

        collab = _collaborative_filter(user, limit=min(limit, 10))
        if collab:
            sections.append({
                "title": "Customers Like You Also Loved",
                "subtitle": "What similar shoppers are buying",
                "strategy": "collaborative",
                "products": _serialize(collab),
            })

        trending = get_trending_products(limit=min(limit, 10))
        sections.append({
            "title": "Trending Now",
            "subtitle": "Hot across the marketplace",
            "strategy": "popularity",
            "products": _serialize(trending),
        })

        # Price-matched picks
        price_picks = _price_affinity_picks(user, limit=min(limit, 8))
        if price_picks:
            sections.append({
                "title": "In Your Price Range",
                "subtitle": f"Great picks around ZMW {prefs.get('price_range', {}).get('avg', '0')}",
                "strategy": "price_affinity",
                "products": _serialize(price_picks),
            })

    return sections


# ===================================================================
# Internal: hybrid computation
# ===================================================================

def _compute_hybrid(user, limit: int) -> list[dict[str, Any]]:
    """Run all signal scorers and merge into a single ranking."""
    prefs = _get_or_compute_preferences(user)
    user_engaged = _user_engaged_product_ids(user)

    # Candidate pool: products the user hasn't engaged with
    candidates = _visible_products().exclude(pk__in=user_engaged)

    if not candidates.exists():
        # Fallback to trending if no candidates
        return [
            {"product": p, "score": float(i), "strategy": "popularity"}
            for i, p in enumerate(get_trending_products(limit))
        ]

    # Gather per-signal scores
    collab_scores = _collaborative_scores(user, candidates)
    content_scores = _content_scores(prefs, candidates)
    pop_scores = _popularity_scores(candidates)
    purchase_scores = _purchase_history_scores(user, candidates)
    price_scores = _price_affinity_scores(prefs, candidates)

    # Merge
    all_product_ids = set()
    for scores in [collab_scores, content_scores, pop_scores, purchase_scores, price_scores]:
        all_product_ids.update(scores.keys())

    product_map = {
        p.pk: p
        for p in candidates.filter(pk__in=all_product_ids).select_related("store", "category")
    }

    merged = []
    for pid in all_product_ids:
        if pid not in product_map:
            continue
        hybrid = (
            WEIGHTS["collaborative"] * collab_scores.get(pid, 0.0)
            + WEIGHTS["content_based"] * content_scores.get(pid, 0.0)
            + WEIGHTS["popularity"] * pop_scores.get(pid, 0.0)
            + WEIGHTS["purchase_history"] * purchase_scores.get(pid, 0.0)
            + WEIGHTS["price_affinity"] * price_scores.get(pid, 0.0)
        )
        # Determine dominant strategy
        component_scores = {
            "collaborative": collab_scores.get(pid, 0.0),
            "content_based": content_scores.get(pid, 0.0),
            "popularity": pop_scores.get(pid, 0.0),
            "purchase_history": purchase_scores.get(pid, 0.0),
        }
        dominant = max(component_scores, key=component_scores.get)

        merged.append({
            "product": product_map[pid],
            "score": round(hybrid, 6),
            "strategy": dominant,
        })

    merged.sort(key=lambda x: x["score"], reverse=True)

    # Ensure diversity — no more than 40% from a single category
    return _diversify(merged, limit)


def _diversify(recs: list[dict], limit: int, max_category_ratio: float = 0.4) -> list[dict]:
    """Ensure category diversity in the final ranking."""
    if not recs:
        return []

    max_per_cat = max(1, int(limit * max_category_ratio))
    cat_counts: Counter = Counter()
    result = []

    for rec in recs:
        cat_id = rec["product"].category_id
        if cat_counts[cat_id] < max_per_cat:
            result.append(rec)
            cat_counts[cat_id] += 1
        if len(result) >= limit:
            break

    # Fill remaining slots if diversity filtering was too aggressive
    if len(result) < limit:
        for rec in recs:
            if rec not in result:
                result.append(rec)
            if len(result) >= limit:
                break

    return result


# ===================================================================
# Internal: individual signal scorers
# ===================================================================

def _collaborative_scores(user, candidates) -> dict[int, float]:
    """
    "Users who bought/liked X also bought/liked Y"
    Find users who share engagement with the current user,
    then boost products they engage with.
    """
    user_items = _user_engaged_product_ids(user)
    if not user_items:
        return {}

    # Find users who engaged with the same products
    similar_user_qs = (
        ProductLike.objects.filter(product_id__in=user_items)
        .exclude(user=user)
        .values("user_id")
        .annotate(overlap=Count("id"))
        .order_by("-overlap")[:100]
    )
    similar_user_ids = [r["user_id"] for r in similar_user_qs]

    if not similar_user_ids:
        return {}

    # Products these similar users engage with
    item_scores: Counter = Counter()
    for product_id in (
        ProductLike.objects.filter(user_id__in=similar_user_ids)
        .values_list("product_id", flat=True)
    ):
        item_scores[product_id] += 1
    for product_id in (
        OrderLine.objects.filter(order__buyer_id__in=similar_user_ids)
        .values_list("product_id", flat=True)
    ):
        item_scores[product_id] += 2  # Purchases weighted higher

    if not item_scores:
        return {}

    max_score = max(item_scores.values())
    candidate_ids = set(candidates.values_list("pk", flat=True))

    return {
        pid: item_scores[pid] / max_score
        for pid in candidate_ids
        if pid in item_scores
    }


def _content_scores(prefs: dict, candidates) -> dict[int, float]:
    """Score candidates by overlap with user's category + tag preferences."""
    cat_weights = prefs.get("category_weights", {})
    tag_weights = prefs.get("tag_weights", {})

    if not cat_weights and not tag_weights:
        return {}

    candidate_list = list(
        candidates.select_related("category").only(
            "pk", "category_id", "suggested_tags", "price"
        )
    )

    scores = {}
    for p in candidate_list:
        score = 0.0
        # Category match
        cat_name = p.category.name.lower() if p.category else ""
        if cat_name in cat_weights:
            score += cat_weights[cat_name] * 0.6
        # Tag overlap
        for tag in (p.suggested_tags or []):
            tag_lower = tag.lower()
            if tag_lower in tag_weights:
                score += tag_weights[tag_lower] * 0.4
        if score > 0:
            scores[p.pk] = min(score, 1.0)

    return scores


def _popularity_scores(candidates) -> dict[int, float]:
    """Score by platform-wide engagement (likes + buys + views)."""
    cutoff = timezone.now() - timedelta(days=30)

    like_counts = dict(
        ProductLike.objects.filter(created_at__gte=cutoff)
        .values_list("product_id")
        .annotate(c=Count("id"))
        .values_list("product_id", "c")
    )
    buy_counts = dict(
        OrderLine.objects.filter(order__created_at__gte=cutoff)
        .values_list("product_id")
        .annotate(c=Count("id"))
        .values_list("product_id", "c")
    )

    scores = {}
    candidate_ids = set(candidates.values_list("pk", flat=True))
    for pid in candidate_ids:
        score = like_counts.get(pid, 0) + 2 * buy_counts.get(pid, 0)
        if score > 0:
            scores[pid] = score

    max_score = max(scores.values()) if scores else 1
    return {pid: s / max_score for pid, s in scores.items()}


def _purchase_history_scores(user, candidates) -> dict[int, float]:
    """Boost products in categories the user has previously purchased."""
    purchased_cats = (
        OrderLine.objects.filter(order__buyer=user)
        .values_list("product_id", flat=True)
    )
    cat_ids = set(
        Product.objects.filter(pk__in=purchased_cats)
        .values_list("category_id", flat=True)
    )

    if not cat_ids:
        return {}

    scores = {}
    candidate_list = candidates.only("pk", "category_id")
    for p in candidate_list:
        if p.category_id in cat_ids:
            scores[p.pk] = 0.7  # Base boost for matching purchased category

    # Extra boost for products from the same store the user bought from
    bought_store_ids = set(
        Order.objects.filter(buyer=user)
        .values_list("seller_id", flat=True)
    )
    if bought_store_ids:
        for p in candidate_list:
            if p.store_id in bought_store_ids:
                scores[p.pk] = min(scores.get(p.pk, 0.0) + 0.3, 1.0)

    return scores


def _price_affinity_scores(prefs: dict, candidates) -> dict[int, float]:
    """Score candidates by how well their price matches the user's spend band."""
    price_range = prefs.get("price_range", {})
    avg_price = price_range.get("avg")
    if not avg_price:
        return {}

    avg = float(avg_price)
    if avg <= 0:
        return {}

    scores = {}
    for p in candidates.only("pk", "price"):
        price = float(p.price)
        # Gaussian-like scoring: peak at avg, taper off
        ratio = price / avg if avg > 0 else 1.0
        score = math.exp(-((ratio - 1.0) ** 2) * 2)
        scores[p.pk] = round(score, 4)

    return scores


def _price_affinity_picks(user, limit: int = 8) -> list[Product]:
    """Get products in the user's preferred price range."""
    prefs = _get_or_compute_preferences(user)
    price_range = prefs.get("price_range", {})
    avg = price_range.get("avg")
    if not avg:
        return []

    avg_f = float(avg)
    low = avg_f * 0.5
    high = avg_f * 1.5
    engaged = _user_engaged_product_ids(user)

    return list(
        _visible_products()
        .exclude(pk__in=engaged)
        .filter(price__gte=Decimal(str(low)), price__lte=Decimal(str(high)))
        .order_by("-created_at")[:limit]
    )


# ===================================================================
# Internal: collaborative filter (used by get_similar_users_top_picks)
# ===================================================================

def _collaborative_filter(user, limit: int = 10) -> list[Product]:
    """Shortcut: products bought by similar users."""
    prefs = _get_or_compute_preferences(user)
    top_cats = sorted(
        prefs.get("category_weights", {}),
        key=prefs.get("category_weights", {}).get,
        reverse=True,
    )[:5]

    if not top_cats:
        return []

    similar_users = (
        UserPreference.objects.filter(category_weights__has_any_keys=top_cats)
        .exclude(user=user)
        .order_by("-engagement_score")[:30]
    )

    if not similar_users:
        return []

    similar_user_ids = [up.user_id for up in similar_users]
    engaged = _user_engaged_product_ids(user)

    return list(
        _visible_products()
        .filter(
            Q(likes__user_id__in=similar_user_ids)
            | Q(wishlist_entries__user_id__in=similar_user_ids)
            | Q(orderline__order__buyer_id__in=similar_user_ids)
        )
        .exclude(pk__in=engaged)
        .distinct()
        .order_by("-created_at")[:limit]
    )


# ===================================================================
# Internal: preferences & helpers
# ===================================================================

def _get_or_compute_preferences(user) -> dict:
    """Get or build user preference profile."""
    try:
        pref = UserPreference.objects.get(user=user)
        return {
            "category_weights": pref.category_weights,
            "tag_weights": pref.tag_weights,
            "price_range": pref.price_range,
            "engagement_score": pref.engagement_score,
        }
    except UserPreference.DoesNotExist:
        return _build_preferences(user)


def _build_preferences(user) -> dict:
    """Build preferences from scratch and persist."""
    category_counter: Counter = Counter()
    tag_counter: Counter = Counter()
    prices: list[float] = []

    # From likes
    liked_products = Product.objects.filter(likes__user=user).select_related("category")
    for p in liked_products:
        if p.category:
            category_counter[p.category.name.lower()] += 2
        for tag in (p.suggested_tags or []):
            tag_counter[tag.lower()] += 2
        prices.append(float(p.price))

    # From purchases
    purchased_ids = OrderLine.objects.filter(
        order__buyer=user
    ).values_list("product_id", flat=True)
    purchased_products = Product.objects.filter(pk__in=purchased_ids).select_related("category")
    for p in purchased_products:
        if p.category:
            category_counter[p.category.name.lower()] += 3
        for tag in (p.suggested_tags or []):
            tag_counter[tag.lower()] += 3
        prices.append(float(p.price))

    # From wishlist
    wishlist_products = Product.objects.filter(wishlist_entries__user=user).select_related("category")
    for p in wishlist_products:
        if p.category:
            category_counter[p.category.name.lower()] += 2
        for tag in (p.suggested_tags or []):
            tag_counter[tag.lower()] += 2

    # From views (lower weight)
    viewed_ids = ProductView.objects.filter(user=user).values_list("product_id", flat=True)
    viewed_products = Product.objects.filter(pk__in=viewed_ids).select_related("category")
    for p in viewed_products:
        if p.category:
            category_counter[p.category.name.lower()] += 1
        for tag in (p.suggested_tags or []):
            tag_counter[tag.lower()] += 1
        prices.append(float(p.price))

    # Normalise weights
    if category_counter:
        max_cat = max(category_counter.values())
        category_weights = {k: v / max_cat for k, v in category_counter.items()}
    else:
        category_weights = {}

    if tag_counter:
        max_tag = max(tag_counter.values())
        tag_weights = {k: v / max_tag for k, v in tag_counter.most_common(50)}
    else:
        tag_weights = {}

    # Price range
    price_range = {}
    if prices:
        sorted_prices = sorted(prices)
        price_range = {
            "min": min(prices),
            "max": max(prices),
            "avg": sum(prices) / len(prices),
            "median": sorted_prices[len(sorted_prices) // 2],
        }

    engagement_score = (
        len(list(ProductLike.objects.filter(user=user)))
        + 2 * Order.objects.filter(buyer=user).count()
        + 0.5 * ProductView.objects.filter(user=user).count()
    )

    # Top products (most engaged)
    top_products = list(
        ProductLike.objects.filter(user=user)
        .values_list("product_id", flat=True)[:10]
    )

    prefs = {
        "category_weights": category_weights,
        "tag_weights": tag_weights,
        "price_range": price_range,
        "engagement_score": engagement_score,
        "top_products": top_products,
    }

    # Persist
    UserPreference.objects.update_or_create(
        user=user,
        defaults={
            "category_weights": category_weights,
            "tag_weights": tag_weights,
            "price_range": price_range,
            "engagement_score": engagement_score,
            "top_products": top_products,
        },
    )

    return prefs


def _is_cold_start(user, prefs: dict) -> bool:
    """Check if user doesn't have enough history for personalisation."""
    engagement = prefs.get("engagement_score", 0) if prefs else 0
    return engagement < MIN_EVENTS_FOR_PERSONALISATION


def _user_engaged_product_ids(user) -> set[int]:
    """All product IDs the user has interacted with."""
    ids = set()
    ids.update(ProductLike.objects.filter(user=user).values_list("product_id", flat=True))
    ids.update(Wishlist.objects.filter(user=user).values_list("product_id", flat=True))
    ids.update(
        OrderLine.objects.filter(order__buyer=user).values_list("product_id", flat=True)
    )
    ids.update(ProductView.objects.filter(user=user).values_list("product_id", flat=True))
    ids.update(ProductRating.objects.filter(user=user).values_list("product_id", flat=True))
    return ids


def _visible_products():
    """Base queryset of products visible to buyers."""
    return (
        Product.objects.filter(
            status=Product.Status.APPROVED,
            store__status=Store.Status.APPROVED,
        )
        .select_related("store", "category")
        .prefetch_related("images")
    )


def _price_band_q(price: Decimal) -> Q:
    """Q filter for products within ±40% of the given price."""
    low = float(price) * 0.6
    high = float(price) * 1.4
    return Q(price__gte=Decimal(str(low)), price__lte=Decimal(str(high)))


def _get_fresh_cache(user, strategy, limit):
    """Return cached recommendations if they are less than 1 hour old."""
    cutoff = timezone.now() - timedelta(hours=1)
    qs = ProductRecommendation.objects.filter(
        user=user,
        generated_at__gte=cutoff,
    )
    if strategy:
        qs = qs.filter(strategy=strategy)
    else:
        qs = qs.filter(strategy=ProductRecommendation.Strategy.HYBRID)

    cached = list(qs.select_related("product", "product__store", "product__category").order_by("-score")[:limit])
    if len(cached) >= limit:
        return [rec.product for rec in cached]
    return None


def _save_cache(user, recs: list[dict], strategy: str):
    """Persist recommendation results to cache table."""
    with transaction.atomic():
        ProductRecommendation.objects.filter(user=user, strategy=strategy).delete()
        ProductRecommendation.objects.bulk_create([
            ProductRecommendation(
                user=user,
                product=r["product"],
                score=r["score"],
                strategy=strategy,
                position=i,
            )
            for i, r in enumerate(recs)
        ])


def _serialize(products: list[Product]) -> list[dict[str, Any]]:
    """Minimal product serialisation for the For You feed."""
    from apps.products.serializers import PublicProductListSerializer
    return PublicProductListSerializer(
        products, many=True, context={"request": None}
    ).data
