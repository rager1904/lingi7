"""
apps/recommendations/views.py
==============================
API views for the per-user recommendation system.

Endpoints:
    POST   /api/v1/recommendations/like/          — toggle like
    GET    /api/v1/recommendations/likes/          — list liked products
    POST   /api/v1/recommendations/view/           — track product view
    POST   /api/v1/recommendations/rate/           — rate a product
    GET    /api/v1/recommendations/ratings/         — list user ratings
    POST   /api/v1/recommendations/wishlist/        — add to wishlist
    DELETE /api/v1/recommendations/wishlist/<pk>/    — remove from wishlist
    GET    /api/v1/recommendations/wishlist/         — list wishlist items
    GET    /api/v1/recommendations/for-you/          — personalised feed
    GET    /api/v1/recommendations/trending/          — trending products
    GET    /api/v1/recommendations/similar/<id>/      — similar products
    GET    /api/v1/recommendations/stats/             — engagement stats
"""

from __future__ import annotations

import logging

from django.db import IntegrityError
from django.db.models import Avg, Count
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.products.models import Product
from apps.products.serializers import PublicProductListSerializer

from .models import ProductLike, ProductRating, ProductView, Wishlist, UserPreference
from .serializers import (
    EngagementStatsSerializer,
    ProductLikeSerializer,
    ProductRatingSerializer,
    ProductViewSerializer,
    WishlistCreateSerializer,
    WishlistSerializer,
)
from .services import (
    get_for_you_feed,
    get_recommendations,
    get_similar_products,
    get_similar_users_top_picks,
    get_trending_products,
)

logger = logging.getLogger(__name__)


# ===================================================================
# Like / Unlike
# ===================================================================

class LikeToggleView(APIView):
    """POST to toggle a like on/off for a product."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"

    def post(self, request):
        product_id = request.data.get("product_id")
        if not product_id:
            return Response(
                {"error": {"code": "missing_field", "message": "product_id is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            product = Product.objects.get(pk=product_id, status=Product.Status.APPROVED)
        except Product.DoesNotExist:
            return Response(
                {"error": {"code": "not_found", "message": "Product not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )

        like, created = ProductLike.objects.get_or_create(
            user=request.user, product=product
        )
        if not created:
            like.delete()
            return Response({"liked": False, "product_id": product_id})

        return Response({"liked": True, "product_id": product_id}, status=status.HTTP_201_CREATED)


class LikesListView(APIView):
    """GET all products the current user has liked."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"

    def get(self, request):
        likes = (
            ProductLike.objects.filter(user=request.user)
            .select_related("product", "product__store", "product__category")
            .prefetch_related("product__images")
            .order_by("-created_at")
        )
        product_ids = [like.product_id for like in likes]
        products = {
            p.pk: p
            for p in Product.objects.filter(pk__in=product_ids, status=Product.Status.APPROVED)
        }
        ordered = [products[pid] for pid in product_ids if pid in products]
        data = PublicProductListSerializer(ordered, many=True, context={"request": request}).data
        return Response({"results": data, "count": len(data)})


# ===================================================================
# View tracking
# ===================================================================

class TrackProductView(APIView):
    """POST to record a product view (deduplicated per user+product)."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"

    def post(self, request):
        product_id = request.data.get("product_id")
        if not product_id:
            return Response(
                {"error": {"code": "missing_field", "message": "product_id is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            product = Product.objects.get(pk=product_id, status=Product.Status.APPROVED)
        except Product.DoesNotExist:
            return Response(
                {"error": {"code": "not_found", "message": "Product not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )

        view_obj, created = ProductView.objects.get_or_create(
            user=request.user, product=product
        )
        if not created:
            view_obj.view_count += 1
            view_obj.save(update_fields=["view_count", "last_viewed_at"])

        return Response({"tracked": True, "view_count": view_obj.view_count})


# ===================================================================
# Ratings
# ===================================================================

class RateProductView(APIView):
    """POST to rate a product (1-5 stars) with optional review text."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"

    def post(self, request):
        product_id = request.data.get("product_id")
        score = request.data.get("score")
        review = request.data.get("review", "")

        if not product_id or score is None:
            return Response(
                {"error": {"code": "missing_field", "message": "product_id and score are required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            score = int(score)
            if not (1 <= score <= 5):
                raise ValueError
        except (ValueError, TypeError):
            return Response(
                {"error": {"code": "invalid_score", "message": "Score must be an integer between 1 and 5."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            product = Product.objects.get(pk=product_id, status=Product.Status.APPROVED)
        except Product.DoesNotExist:
            return Response(
                {"error": {"code": "not_found", "message": "Product not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )

        rating, created = ProductRating.objects.update_or_create(
            user=request.user,
            product=product,
            defaults={"score": score, "review": review},
        )

        return Response(
            ProductRatingSerializer(rating).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class RatingsListView(APIView):
    """GET all ratings by the current user."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"

    def get(self, request):
        ratings = (
            ProductRating.objects.filter(user=request.user)
            .select_related("product", "product__store")
            .order_by("-created_at")
        )
        data = ProductRatingSerializer(ratings, many=True).data
        return Response({"results": data, "count": len(data)})


# ===================================================================
# Wishlist
# ===================================================================

class WishlistListCreateView(APIView):
    """GET/POST wishlist items."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"

    def get(self, request):
        items = (
            Wishlist.objects.filter(user=request.user)
            .select_related("product", "product__store", "product__category")
            .prefetch_related("product__images")
            .order_by("-created_at")
        )
        data = WishlistSerializer(items, many=True).data
        return Response({"results": data, "count": len(data)})

    def post(self, request):
        serializer = WishlistCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            product = Product.objects.get(pk=data["product_id"], status=Product.Status.APPROVED)
        except Product.DoesNotExist:
            return Response(
                {"error": {"code": "not_found", "message": "Product not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            entry = Wishlist.objects.create(
                user=request.user,
                product=product,
                name=data.get("name", "My Wishlist"),
                note=data.get("note", ""),
            )
        except IntegrityError:
            return Response(
                {"error": {"code": "already_saved", "message": "Product is already in your wishlist."}},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(WishlistSerializer(entry).data, status=status.HTTP_201_CREATED)


class WishlistDeleteView(APIView):
    """DELETE a wishlist item."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"

    def delete(self, request, pk):
        try:
            item = Wishlist.objects.get(pk=pk, user=request.user)
        except Wishlist.DoesNotExist:
            return Response(
                {"error": {"code": "not_found", "message": "Wishlist item not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ===================================================================
# Recommendations
# ===================================================================

class ForYouView(APIView):
    """GET personalised 'For You' feed with multiple recommendation sections."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"

    def get(self, request):
        limit = min(int(request.query_params.get("limit", 20)), 50)
        sections = get_for_you_feed(request.user, limit=limit)
        return Response({"success": True, "data": sections})


class TrendingView(APIView):
    """GET platform-wide trending products."""
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"

    def get(self, request):
        limit = min(int(request.query_params.get("limit", 20)), 50)
        products = get_trending_products(limit=limit)
        data = PublicProductListSerializer(products, many=True, context={"request": request}).data
        return Response({"success": True, "source": "trending", "data": data})


class SimilarProductsView(APIView):
    """GET products similar to a given product (enhanced version)."""
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"

    def get(self, request, product_id):
        limit = min(int(request.query_params.get("limit", 10)), 30)
        try:
            product = Product.objects.get(pk=product_id, status=Product.Status.APPROVED)
        except Product.DoesNotExist:
            return Response(
                {"error": {"code": "not_found", "message": "Product not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )

        products = get_similar_products(product, limit=limit)
        data = PublicProductListSerializer(products, many=True, context={"request": request}).data
        return Response({"success": True, "source": "content-similarity", "data": data})


class EngagementStatsView(APIView):
    """GET the current user's engagement statistics."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"

    def get(self, request):
        user = request.user
        total_likes = ProductLike.objects.filter(user=user).count()
        total_views = ProductView.objects.filter(user=user).count()
        total_ratings = ProductRating.objects.filter(user=user).count()
        total_wishlist = Wishlist.objects.filter(user=user).count()
        avg_rating = ProductRating.objects.filter(user=user).aggregate(avg=Avg("score"))["avg"]

        # Top categories from preferences
        try:
            pref = UserPreference.objects.get(user=user)
            top_cats = sorted(
                pref.category_weights,
                key=pref.category_weights.get,
                reverse=True,
            )[:5]
            engagement_score = pref.engagement_score
        except UserPreference.DoesNotExist:
            top_cats = []
            engagement_score = 0.0

        stats = {
            "total_likes": total_likes,
            "total_views": total_views,
            "total_ratings": total_ratings,
            "total_wishlist_items": total_wishlist,
            "avg_rating_given": avg_rating,
            "top_categories": top_cats,
            "engagement_score": engagement_score,
        }
        return Response(EngagementStatsSerializer(stats).data)
