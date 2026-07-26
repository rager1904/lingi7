"""
apps/products/serializers.py
============================
DRF serializers for the products domain.

Serializers are data-shape definitions only — no business logic.
All mutations go through ProductService / StoreService.

Serializer groups:
    Public (buyer-facing):
        CategorySerializer
        PublicProductListSerializer
        PublicProductDetailSerializer

    Vendor-facing:
        StoreRegistrationSerializer
        StoreDetailSerializer
        VendorProductSerializer
        ProductImageUploadSerializer
        StoreDashboardSerializer

    Admin-facing:
        AdminStoreSerializer
        AdminProductSerializer
"""

from __future__ import annotations

from rest_framework import serializers

from apps.products.models import Category, InventoryRecord, Product, ProductImage, Store


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------

class CategorySerializer(serializers.ModelSerializer):
    """Shallow category representation for public use."""

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "parent", "icon", "position"]


class CategoryTreeSerializer(serializers.ModelSerializer):
    """Recursive category tree — children nested to 2 levels."""

    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "icon", "children"]

    def get_children(self, obj: Category) -> list:
        qs = obj.children.filter(is_active=True)
        return CategorySerializer(qs, many=True).data


# ---------------------------------------------------------------------------
# Product images
# ---------------------------------------------------------------------------

class ProductImageSerializer(serializers.ModelSerializer):
    """Read-only image representation."""

    class Meta:
        model = ProductImage
        fields = ["id", "image", "alt_text", "position"]


class ProductImageUploadSerializer(serializers.Serializer):
    """Validates a single image upload from vendor."""

    image = serializers.ImageField(max_length=None, allow_empty_file=False)
    alt_text = serializers.CharField(max_length=200, required=False, default="")


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

class InventorySerializer(serializers.ModelSerializer):
    """Read-only inventory snapshot — vendor dashboard only."""

    class Meta:
        model = InventoryRecord
        fields = [
            "quantity_available",
            "quantity_held",
            "quantity_on_hand",
            "low_stock_threshold",
            "track_inventory",
            "allow_backorder",
            "is_in_stock",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Public product serializers (buyer-facing)
# ---------------------------------------------------------------------------

class PublicProductListSerializer(serializers.ModelSerializer):
    """Lightweight product card for catalogue listings."""

    primary_image = serializers.SerializerMethodField()
    store_name = serializers.CharField(source="store.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "price",
            "compare_at_price",
            "condition",
            "primary_image",
            "store_name",
            "category_name",
        ]

    def get_primary_image(self, obj: Product) -> str | None:
        img = obj.images.filter(position=0).first()
        if img and img.image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(img.image.url)
            return img.image.url
        return None


class PublicProductDetailSerializer(serializers.ModelSerializer):
    """Full product detail for the buyer-facing product page."""

    images = ProductImageSerializer(many=True, read_only=True)
    category = CategorySerializer(read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    store_slug = serializers.CharField(source="store.slug", read_only=True)
    is_in_stock = serializers.BooleanField(
        source="inventory.is_in_stock", read_only=True
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "price",
            "compare_at_price",
            "condition",
            "weight_kg",
            "ships_from",
            "images",
            "category",
            "store_name",
            "store_slug",
            "is_in_stock",
        ]


# ---------------------------------------------------------------------------
# Store serializers (vendor-facing)
# ---------------------------------------------------------------------------

class StoreRegistrationSerializer(serializers.ModelSerializer):
    """
    Validates the initial store registration payload from a vendor.
    The owner and status fields are set by StoreService — not from input.
    """

    class Meta:
        model = Store
        fields = [
            "name",
            "description",
            "business_type",
            "tpin",
            "nrc_or_reg_no",
            "id_document",
            "business_address",
            "phone_number",
            "payout_account",
            "payout_provider",
        ]

    def validate_name(self, value: str) -> str:
        if Store.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError(
                "A store with this name already exists."
            )
        return value


class StoreDetailSerializer(serializers.ModelSerializer):
    """Vendor's own store read — includes status and audit fields."""

    class Meta:
        model = Store
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "logo",
            "banner",
            "status",
            "rejection_reason",
            "business_type",
            "payout_account",
            "payout_provider",
            "transaction_fee_rate",
            "total_gmv",
            "created_at",
        ]
        read_only_fields = [
            "slug",
            "status",
            "rejection_reason",
            "transaction_fee_rate",
            "total_gmv",
            "created_at",
        ]


class StoreDashboardSerializer(serializers.Serializer):
    """
    Aggregated KPI snapshot for the vendor dashboard.
    Computed in the view from DB aggregations — not a model serializer.
    """

    store_name = serializers.CharField()
    store_status = serializers.CharField()
    total_products = serializers.IntegerField()
    pending_listings = serializers.IntegerField()
    active_listings = serializers.IntegerField()
    orders_pending_shipment = serializers.IntegerField()
    escrow_held_zmw = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_gmv_zmw = serializers.DecimalField(max_digits=14, decimal_places=2)
    dispute_rate_pct = serializers.DecimalField(max_digits=5, decimal_places=2)
    last_payout_at = serializers.DateTimeField(allow_null=True)
    last_payout_zmw = serializers.DecimalField(
        max_digits=12, decimal_places=2, allow_null=True
    )


# ---------------------------------------------------------------------------
# Vendor product serializers
# ---------------------------------------------------------------------------

class VendorProductSerializer(serializers.ModelSerializer):
    """
    Vendor-facing product create/update.

    On create: initial_quantity and track_inventory are forwarded to
    ProductService.create_product() for InventoryRecord creation.
    """

    images = ProductImageSerializer(many=True, read_only=True)
    inventory = InventorySerializer(read_only=True)
    initial_quantity = serializers.IntegerField(
        min_value=0, default=0, write_only=True, required=False
    )
    track_inventory = serializers.BooleanField(
        default=True, write_only=True, required=False
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "category",
            "sku",
            "condition",
            "price",
            "compare_at_price",
            "weight_kg",
            "ships_from",
            "status",
            "rejection_reason",
            "images",
            "inventory",
            "initial_quantity",
            "track_inventory",
        ]
        read_only_fields = [
            "slug",
            "status",
            "rejection_reason",
            "images",
            "inventory",
        ]


# ---------------------------------------------------------------------------
# Admin serializers
# ---------------------------------------------------------------------------

class AdminStoreSerializer(serializers.ModelSerializer):
    """Full store representation for admin review."""

    owner_email = serializers.EmailField(source="owner.email", read_only=True)
    owner_phone = serializers.CharField(
        source="owner.phone_number", read_only=True
    )

    class Meta:
        model = Store
        fields = "__all__"
        read_only_fields = ["owner", "created_at", "updated_at"]


class AdminProductSerializer(serializers.ModelSerializer):
    """Full product representation for admin listing review."""

    store_name = serializers.CharField(source="store.name", read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    inventory = InventorySerializer(read_only=True)

    class Meta:
        model = Product
        fields = "__all__"
        read_only_fields = ["store", "slug", "created_at", "updated_at"]
