"""
apps/recommendations/serializers.py
====================================
DRF serializers for the recommendations app.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.products.serializers import PublicProductListSerializer

from .models import ProductLike, ProductRating, ProductView, Wishlist


# ---------------------------------------------------------------------------
# Activity tracking
# ---------------------------------------------------------------------------

class ProductLikeSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = ProductLike
        fields = ["id", "product", "product_name", "created_at"]
        read_only_fields = ["id", "created_at"]


class ProductViewSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = ProductView
        fields = [
            "id",
            "product",
            "product_name",
            "view_count",
            "first_viewed_at",
            "last_viewed_at",
        ]
        read_only_fields = fields


class ProductRatingSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = ProductRating
        fields = [
            "id",
            "product",
            "product_name",
            "score",
            "review",
            "user_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_user_name(self, obj) -> str:
        return obj.user.get_full_name() or str(obj.user.phone_number)


class WishlistSerializer(serializers.ModelSerializer):
    product_detail = PublicProductListSerializer(source="product", read_only=True)

    class Meta:
        model = Wishlist
        fields = ["id", "name", "product", "product_detail", "note", "created_at"]
        read_only_fields = ["id", "created_at"]


class WishlistCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    name = serializers.CharField(max_length=120, default="My Wishlist")
    note = serializers.CharField(max_length=300, required=False, allow_blank=True)


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

class RecommendationSectionSerializer(serializers.Serializer):
    title = serializers.CharField()
    subtitle = serializers.CharField()
    strategy = serializers.CharField()
    products = PublicProductListSerializer(many=True)


class ForYouResponseSerializer(serializers.Serializer):
    sections = RecommendationSectionSerializer(many=True)


class EngagementStatsSerializer(serializers.Serializer):
    total_likes = serializers.IntegerField()
    total_views = serializers.IntegerField()
    total_ratings = serializers.IntegerField()
    total_wishlist_items = serializers.IntegerField()
    avg_rating_given = serializers.FloatField(allow_null=True)
    top_categories = serializers.ListField(child=serializers.CharField())
    engagement_score = serializers.FloatField()
