"""
apps/products/models.py
=======================
Product catalogue models for Lingi7.

Covers:
    - Category taxonomy (self-referential, up to 3 levels)
    - Store (multi-tenant vendor unit — one per VENDOR user)
    - Product (listing with approval state machine)
    - ProductImage (S3-backed, ordered)
    - InventoryRecord (stock tracking per product)

All vendor-facing data is scoped through Store FK.
Product and Store status machines are enforced in the service layer only.

Reference: LG7-BE-011 | Phase 1 MVP
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------

class Category(models.Model):
    """
    Self-referential category tree — maximum 3 levels (root → sub → leaf).

    root:  Electronics
    sub:   Mobile Phones
    leaf:  Smartphones

    Ordering: position (ascending) within the same parent, then name.
    """

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=60, blank=True)  # CSS class or S3 key
    position = models.PositiveSmallIntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["position", "name"]
        indexes = [
            models.Index(fields=["parent", "is_active"]),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:  # type: ignore[override]
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Store (multi-tenant vendor unit)
# ---------------------------------------------------------------------------

class Store(models.Model):
    """
    Central tenant unit.  One store per VENDOR account.

    All vendor data (products, orders, payouts) references this model via FK.
    Status transitions are enforced by StoreService — never set status directly.

    KYC fields satisfy BoZ KYC requirements:
        full name (via owner User), NRC / PACRA reg, physical address, phone.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Admin Review"
        APPROVED = "APPROVED", "Approved & Live"
        REJECTED = "REJECTED", "Rejected"
        SUSPENDED = "SUSPENDED", "Suspended"

    class BusinessType(models.TextChoices):
        INDIVIDUAL = "INDIVIDUAL", "Individual Trader"
        REGISTERED = "REGISTERED", "Registered Business (PACRA)"

    class PayoutProvider(models.TextChoices):
        MTN = "MTN", "MTN MoMo"
        AIRTEL = "AIRTEL", "Airtel Money"

    # Identity
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="store",
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to="stores/logos/", null=True, blank=True)
    banner = models.ImageField(upload_to="stores/banners/", null=True, blank=True)

    # Status & admin control
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_stores",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    suspension_reason = models.TextField(blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)

    # Zambian KYC / compliance fields
    business_type = models.CharField(
        max_length=20,
        choices=BusinessType.choices,
        default=BusinessType.INDIVIDUAL,
    )
    tpin = models.CharField(max_length=20, blank=True)          # ZRA Tax PIN
    nrc_or_reg_no = models.CharField(max_length=50)              # NRC / PACRA
    id_document = models.FileField(upload_to="stores/kyc/")      # S3-backed
    business_address = models.TextField()
    phone_number = models.CharField(max_length=20)

    # Financials
    transaction_fee_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.0500"),  # 5% platform default
    )
    payout_account = models.CharField(max_length=20, blank=True)
    payout_provider = models.CharField(
        max_length=10,
        choices=PayoutProvider.choices,
        blank=True,
    )
    total_gmv = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["owner"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.status})"

    def save(self, *args, **kwargs) -> None:  # type: ignore[override]
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def is_active(self) -> bool:
        """Return True only when the store is APPROVED."""
        return self.status == self.Status.APPROVED


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------

class Product(models.Model):
    """
    A vendor product listing.

    Status machine: DRAFT → PENDING → APPROVED | REJECTED → ARCHIVED
    Only APPROVED products are visible to buyers.
    Status transitions enforced by ProductService.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING = "PENDING", "Pending Admin Review"
        APPROVED = "APPROVED", "Approved — Live"
        REJECTED = "REJECTED", "Rejected"
        ARCHIVED = "ARCHIVED", "Archived"

    class Condition(models.TextChoices):
        NEW = "NEW", "New"
        USED = "USED", "Used — Good"
        REFURBISHED = "REFURBISHED", "Refurbished"

    # Ownership
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="products",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )

    # Core fields
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    description = models.TextField()
    sku = models.CharField(max_length=80, blank=True, db_index=True)
    condition = models.CharField(
        max_length=20,
        choices=Condition.choices,
        default=Condition.NEW,
    )

    # Pricing (ZMW)
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    compare_at_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    # Status / visibility
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    rejection_reason = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_products",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # Shipping
    weight_kg = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    ships_from = models.CharField(max_length=120, blank=True)  # e.g. "Lusaka", "China"

    # AI / search (populated by Celery tasks in Phase 2)
    embedding = models.JSONField(null=True, blank=True)         # vector placeholder
    embedding_updated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["store", "status"]),
            models.Index(fields=["category", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} [{self.status}]"

    def save(self, *args, **kwargs) -> None:  # type: ignore[override]
        if not self.slug:
            base = slugify(self.name)
            self.slug = f"{base}-{uuid.uuid4().hex[:8]}"
        super().save(*args, **kwargs)

    @property
    def is_visible(self) -> bool:
        """True only when status is APPROVED and the owning store is active."""
        return self.status == self.Status.APPROVED and self.store.is_active


# ---------------------------------------------------------------------------
# ProductImage
# ---------------------------------------------------------------------------

class ProductImage(models.Model):
    """
    Ordered set of images for a product.  Primary image has position=0.
    Images are stored in S3 / Cloudflare R2 via django-storages.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="products/images/")
    alt_text = models.CharField(max_length=200, blank=True)
    position = models.PositiveSmallIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position"]
        indexes = [
            models.Index(fields=["product", "position"]),
        ]

    def __str__(self) -> str:
        return f"Image #{self.position} for {self.product.name}"


# ---------------------------------------------------------------------------
# InventoryRecord
# ---------------------------------------------------------------------------

class InventoryRecord(models.Model):
    """
    Per-product stock tracking.  One record per product (OneToOne).

    quantity_held is decremented when an order moves to HELD escrow state
    and restored if the order is cancelled or refunded.
    """

    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name="inventory",
    )
    quantity_available = models.PositiveIntegerField(default=0)
    quantity_held = models.PositiveIntegerField(default=0)  # reserved by active orders
    low_stock_threshold = models.PositiveIntegerField(default=5)
    track_inventory = models.BooleanField(default=True)
    allow_backorder = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Inventory: {self.product.name} (avail={self.quantity_available})"

    @property
    def quantity_on_hand(self) -> int:
        """Total physical stock including reserved units."""
        return self.quantity_available + self.quantity_held

    @property
    def is_in_stock(self) -> bool:
        """True if available or backordering is allowed."""
        if not self.track_inventory:
            return True
        return self.quantity_available > 0 or self.allow_backorder
