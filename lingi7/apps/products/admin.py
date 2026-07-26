"""
apps/products/admin.py
======================
Django admin configuration for the products domain.

Design rules:
    - Store admin: Approve / Reject / Suspend are admin actions — NOT direct
      field edits.  All transitions route through StoreService.
    - Product admin: Approve / Reject are admin actions — all through ProductService.
    - No delete permission on Store (suspend instead).
    - PENDING items ordered first in both queues for fast triage.
"""

from __future__ import annotations

from django.contrib import admin
from django.db.models import Case, IntegerField, When
from django.utils.html import format_html

from apps.products.enrichment import CatalogEnrichmentService
from apps.products.models import Category, InventoryRecord, Product, ProductImage, Store
from apps.products.services import ProductService, StoreService


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "parent", "position", "is_active"]
    list_filter = ["is_active", "parent"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
    ordering = ["position", "name"]


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = [
        "name", "owner_email", "business_type", "status",
        "payout_provider", "created_at", "approved_by",
    ]
    list_filter = ["status", "business_type", "payout_provider"]
    search_fields = ["name", "owner__email", "nrc_or_reg_no", "tpin"]
    readonly_fields = [
        "owner", "slug", "created_at", "updated_at",
        "approved_by", "approved_at", "suspended_at", "total_gmv",
    ]
    actions = ["action_approve_stores", "action_reject_stores", "action_suspend_stores"]

    def get_queryset(self, request):
        return super().get_queryset(request).order_by(
            Case(
                When(status=Store.Status.PENDING, then=0),
                default=1,
                output_field=IntegerField(),
            ),
            "-created_at",
        )

    def owner_email(self, obj: Store) -> str:
        return obj.owner.email
    owner_email.short_description = "Owner Email"

    def has_delete_permission(self, request, obj=None) -> bool:  # type: ignore[override]
        """Never delete stores — suspend instead."""
        return False

    # ------------------------------------------------------------------
    # Admin actions
    # ------------------------------------------------------------------

    @admin.action(description="Approve selected stores")
    def action_approve_stores(self, request, queryset) -> None:
        approved = 0
        skipped = 0
        for store in queryset:
            try:
                StoreService.approve_store(store=store, admin_user=request.user)
                approved += 1
            except Exception:
                skipped += 1
        self.message_user(
            request,
            f"{approved} store(s) approved. {skipped} skipped (invalid transition).",
        )

    @admin.action(description="Reject selected stores (sets reason: 'See admin notes')")
    def action_reject_stores(self, request, queryset) -> None:
        for store in queryset:
            try:
                StoreService.reject_store(
                    store=store,
                    admin_user=request.user,
                    reason="Application did not meet KYC requirements. See admin notes.",
                )
            except Exception:
                pass
        self.message_user(request, "Selected PENDING stores have been rejected.")

    @admin.action(description="Suspend selected stores")
    def action_suspend_stores(self, request, queryset) -> None:
        for store in queryset:
            try:
                StoreService.suspend_store(
                    store=store,
                    admin_user=request.user,
                    reason="Suspended by admin — pending investigation.",
                )
            except Exception:
                pass
        self.message_user(request, "Selected APPROVED stores have been suspended.")


# ---------------------------------------------------------------------------
# ProductImage (inline)
# ---------------------------------------------------------------------------

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    readonly_fields = ["image_preview", "uploaded_at"]
    fields = ["image_preview", "image", "alt_text", "position", "uploaded_at"]

    def image_preview(self, obj: ProductImage) -> str:
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height:60px;" />', obj.image.url
            )
        return "—"
    image_preview.short_description = "Preview"


# ---------------------------------------------------------------------------
# InventoryRecord (inline)
# ---------------------------------------------------------------------------

class InventoryInline(admin.StackedInline):
    model = InventoryRecord
    extra = 0
    readonly_fields = ["quantity_on_hand", "is_in_stock", "updated_at"]


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        "name", "store", "category", "price",
        "status", "enrichment_status", "condition", "created_at",
    ]
    list_filter = ["status", "enrichment_status", "condition", "store__status"]
    search_fields = ["name", "store__name", "sku", "meta_title"]
    readonly_fields = [
        "slug", "created_at", "updated_at",
        "approved_by", "approved_at", "embedding_updated_at",
        "enriched_at", "enrichment_error",
        "ai_enhanced_title", "ai_features", "ai_specs",
        "suggested_tags", "image_quality_scores", "descriptions_i18n",
        "search_keywords",
    ]
    fieldsets = (
        (None, {
            "fields": (
                "store", "category", "name", "slug", "description", "sku",
                "condition", "price", "compare_at_price", "status", "rejection_reason",
            ),
        }),
        ("Shipping", {
            "fields": ("weight_kg", "ships_from"),
        }),
        ("Catalog enrichment", {
            "fields": (
                "enrichment_status", "enriched_at", "enrichment_error",
                "ai_enhanced_title", "meta_title", "meta_description", "search_keywords",
                "suggested_category", "suggested_tags",
                "ai_features", "ai_specs", "descriptions_i18n", "image_quality_scores",
            ),
        }),
        ("Admin", {
            "fields": ("approved_by", "approved_at", "embedding", "embedding_updated_at", "created_at", "updated_at"),
        }),
    )
    inlines = [ProductImageInline, InventoryInline]
    actions = [
        "action_approve_listings",
        "action_reject_listings",
        "action_archive_listings",
        "action_queue_enrichment",
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).order_by(
            Case(
                When(status=Product.Status.PENDING, then=0),
                default=1,
                output_field=IntegerField(),
            ),
            "-created_at",
        )

    # ------------------------------------------------------------------
    # Admin actions
    # ------------------------------------------------------------------

    @admin.action(description="Approve selected product listings")
    def action_approve_listings(self, request, queryset) -> None:
        approved = 0
        for product in queryset:
            try:
                ProductService.approve_product(
                    product=product, admin_user=request.user
                )
                approved += 1
            except Exception:
                pass
        self.message_user(request, f"{approved} listing(s) approved.")

    @admin.action(description="Reject selected product listings")
    def action_reject_listings(self, request, queryset) -> None:
        for product in queryset:
            try:
                ProductService.reject_product(
                    product=product,
                    admin_user=request.user,
                    reason="Listing does not meet marketplace standards.",
                )
            except Exception:
                pass
        self.message_user(request, "Selected listings have been rejected.")

    @admin.action(description="Archive selected product listings")
    def action_archive_listings(self, request, queryset) -> None:
        for product in queryset:
            try:
                ProductService.archive_product(product=product, actor=request.user)
            except Exception:
                pass
        self.message_user(request, "Selected listings archived.")

    @admin.action(description="Queue AI catalog enrichment for selected products")
    def action_queue_enrichment(self, request, queryset) -> None:
        queued = 0
        for product in queryset:
            try:
                CatalogEnrichmentService.queue_enrichment(product.pk)
                queued += 1
            except Exception:
                pass
        self.message_user(request, f"{queued} product(s) queued for enrichment.")
