"""
apps/products/services.py
=========================
Fat service layer for the products domain.

StoreService   — Store lifecycle (register, approve, reject, suspend)
ProductService — Product listing lifecycle (create, submit, approve, reject,
                 archive, image upload, inventory updates)

Design rules:
    - All state transitions log to AdminAuditLog
    - Views are thin; all business logic lives here
    - select_for_update() used on inventory mutations to prevent races
    - S3 uploads delegated to django-storages; this layer handles metadata only

Reference: LG7-BE-011
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

if TYPE_CHECKING:
    from django.core.files.uploadedfile import InMemoryUploadedFile

from apps.admin_audit.models import AdminAuditLog
from apps.products.exceptions import (
    InsufficientStockError,
    InvalidProductTransitionError,
    InvalidStoreTransitionError,
    StoreError,
)
from apps.products.models import (
    Category,
    InventoryRecord,
    Product,
    ProductImage,
    Store,
)

User = get_user_model()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# StoreService
# ---------------------------------------------------------------------------

class StoreService:
    """
    Manages the full Store lifecycle.

    All status transitions are atomic and write to AdminAuditLog.
    Notification calls are intentionally left as stubs — wire to
    NotificationService when apps/notifications/ is built.
    """

    @staticmethod
    def register_store(owner: Any, validated_data: dict) -> Store:
        """
        Create a new Store in PENDING state for a VENDOR user.

        Args:
            owner: The User instance (must have role=VENDOR).
            validated_data: Cleaned data from StoreRegistrationSerializer.

        Returns:
            The newly created Store instance.

        Raises:
            StoreError: If the user already has a store registered.
        """
        if hasattr(owner, "store"):
            raise StoreError("This user already has a registered store.")

        store: Store = Store.objects.create(
            owner=owner,
            status=Store.Status.PENDING,
            **validated_data,
        )
        logger.info("Store registered: pk=%s owner=%s", store.pk, owner.pk)
        # TODO: NotificationService.send_sms(owner.phone_number, "Store under review.")
        return store

    @staticmethod
    @transaction.atomic
    def approve_store(store: Store, admin_user: Any) -> Store:
        """
        Transition a PENDING Store to APPROVED.

        Args:
            store: The Store to approve.
            admin_user: The admin User performing the action.

        Returns:
            Updated Store instance.

        Raises:
            InvalidStoreTransitionError: If store is not in PENDING state.
        """
        if store.status != Store.Status.PENDING:
            raise InvalidStoreTransitionError(
                f"Cannot approve a store with status '{store.status}'."
            )

        before_state = store.status
        store.status = Store.Status.APPROVED
        store.approved_by = admin_user
        store.approved_at = timezone.now()
        store.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])

        AdminAuditLog.objects.create(
            actor=admin_user,
            action="STORE_APPROVED",
            object_id=str(store.pk),
            before_state=before_state,
            after_state=store.status,
        )
        logger.info("Store approved: pk=%s by admin=%s", store.pk, admin_user.pk)
        # TODO: NotificationService.send_sms(store.owner.phone_number, "Store approved!")
        return store

    @staticmethod
    @transaction.atomic
    def reject_store(store: Store, admin_user: Any, reason: str) -> Store:
        """
        Transition a PENDING Store to REJECTED with a mandatory reason.

        Args:
            store: The Store to reject.
            admin_user: The admin User performing the action.
            reason: Written rejection reason shown to the vendor.

        Returns:
            Updated Store instance.

        Raises:
            InvalidStoreTransitionError: If store is not in PENDING state.
            ValueError: If reason is empty.
        """
        if store.status != Store.Status.PENDING:
            raise InvalidStoreTransitionError(
                f"Cannot reject a store with status '{store.status}'."
            )
        if not reason.strip():
            raise ValueError("A rejection reason is required.")

        before_state = store.status
        store.status = Store.Status.REJECTED
        store.rejection_reason = reason
        store.save(update_fields=["status", "rejection_reason", "updated_at"])

        AdminAuditLog.objects.create(
            actor=admin_user,
            action="STORE_REJECTED",
            object_id=str(store.pk),
            before_state=before_state,
            after_state=store.status,
            notes=reason,
        )
        logger.info("Store rejected: pk=%s reason=%s", store.pk, reason)
        # TODO: NotificationService.send_sms(store.owner.phone_number, f"Store rejected: {reason}")
        return store

    @staticmethod
    @transaction.atomic
    def suspend_store(store: Store, admin_user: Any, reason: str) -> Store:
        """
        Suspend an APPROVED Store.

        Side effect: All APPROVED product listings are immediately ARCHIVED.
        In-flight EscrowAccounts are NOT touched — they follow the escrow
        dispute workflow independently.

        Args:
            store: The Store to suspend.
            admin_user: The admin User performing the action.
            reason: Written suspension reason.

        Returns:
            Updated Store instance.

        Raises:
            InvalidStoreTransitionError: If store is not APPROVED.
            ValueError: If reason is empty.
        """
        if store.status != Store.Status.APPROVED:
            raise InvalidStoreTransitionError(
                f"Cannot suspend a store with status '{store.status}'."
            )
        if not reason.strip():
            raise ValueError("A suspension reason is required.")

        before_state = store.status
        store.status = Store.Status.SUSPENDED
        store.suspension_reason = reason
        store.suspended_at = timezone.now()
        store.save(
            update_fields=["status", "suspension_reason", "suspended_at", "updated_at"]
        )

        # Immediately hide all live listings
        archived_count = store.products.filter(
            status=Product.Status.APPROVED
        ).update(status=Product.Status.ARCHIVED)

        AdminAuditLog.objects.create(
            actor=admin_user,
            action="STORE_SUSPENDED",
            object_id=str(store.pk),
            before_state=before_state,
            after_state=store.status,
            notes=f"{reason} | {archived_count} listings archived",
        )
        logger.warning(
            "Store suspended: pk=%s archived=%d reason=%s",
            store.pk,
            archived_count,
            reason,
        )
        # TODO: NotificationService.send_sms(...)
        return store


# ---------------------------------------------------------------------------
# ProductService
# ---------------------------------------------------------------------------

_PRODUCT_VALID_TRANSITIONS: dict[str, set[str]] = {
    Product.Status.DRAFT:     {Product.Status.PENDING, Product.Status.ARCHIVED},
    Product.Status.PENDING:   {Product.Status.APPROVED, Product.Status.REJECTED, Product.Status.ARCHIVED},
    Product.Status.APPROVED:  {Product.Status.ARCHIVED},
    Product.Status.REJECTED:  {Product.Status.PENDING, Product.Status.ARCHIVED},
    Product.Status.ARCHIVED:  {Product.Status.DRAFT},
}


class ProductService:
    """
    Manages the full Product listing lifecycle.

    State machine:
        DRAFT → PENDING → APPROVED | REJECTED → ARCHIVED
        REJECTED → PENDING  (vendor corrects and resubmits)
        ARCHIVED → DRAFT    (vendor reactivates)
    """

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def create_product(store: Store, validated_data: dict) -> Product:
        """
        Create a new Product in DRAFT state for an approved Store.

        Automatically creates a linked InventoryRecord.

        Args:
            store: The owning Store (must be APPROVED).
            validated_data: Cleaned data from VendorProductSerializer.

        Returns:
            The newly created Product.

        Raises:
            StoreError: If the store is not APPROVED.
        """
        if not store.is_active:
            raise StoreError(
                f"Cannot create a product for a store with status '{store.status}'."
            )

        # Pop nested / non-model fields before create
        initial_quantity: int = validated_data.pop("initial_quantity", 0)
        track_inventory: bool = validated_data.pop("track_inventory", True)

        product: Product = Product.objects.create(
            store=store,
            status=Product.Status.DRAFT,
            **validated_data,
        )

        InventoryRecord.objects.create(
            product=product,
            quantity_available=initial_quantity,
            track_inventory=track_inventory,
        )

        logger.info("Product created: pk=%s store=%s", product.pk, store.pk)
        return product

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------

    @staticmethod
    def _transition(
        product: Product,
        new_status: str,
        actor: Any,
        reason: str = "",
        extra_fields: dict | None = None,
    ) -> Product:
        """
        Internal helper — apply a status transition with audit logging.
        Must be called within an existing atomic block.
        """
        allowed = _PRODUCT_VALID_TRANSITIONS.get(product.status, set())
        if new_status not in allowed:
            raise InvalidProductTransitionError(
                f"Cannot transition product from '{product.status}' to '{new_status}'."
            )

        before_state = product.status
        product.status = new_status
        update_fields = ["status", "updated_at"]

        if extra_fields:
            for field, value in extra_fields.items():
                setattr(product, field, value)
                update_fields.append(field)

        product.save(update_fields=update_fields)

        AdminAuditLog.objects.create(
            actor=actor,
            action=f"PRODUCT_{new_status}",
            object_id=str(product.pk),
            before_state=before_state,
            after_state=new_status,
            notes=reason,
        )
        return product

    @staticmethod
    @transaction.atomic
    def submit_for_review(product: Product, vendor_user: Any) -> Product:
        """
        Move a DRAFT or REJECTED product to PENDING admin review.

        Args:
            product: The Product to submit.
            vendor_user: The authenticated vendor.

        Returns:
            Updated Product.
        """
        return ProductService._transition(
            product=product,
            new_status=Product.Status.PENDING,
            actor=vendor_user,
        )

    @staticmethod
    @transaction.atomic
    def approve_product(product: Product, admin_user: Any) -> Product:
        """
        Approve a PENDING product listing — makes it visible to buyers.

        Args:
            product: The Product to approve.
            admin_user: The admin user.

        Returns:
            Updated Product.
        """
        return ProductService._transition(
            product=product,
            new_status=Product.Status.APPROVED,
            actor=admin_user,
            extra_fields={
                "approved_by": admin_user,
                "approved_at": timezone.now(),
                "rejection_reason": "",
            },
        )

    @staticmethod
    @transaction.atomic
    def reject_product(product: Product, admin_user: Any, reason: str) -> Product:
        """
        Reject a PENDING product with a mandatory reason.

        Args:
            product: The Product to reject.
            admin_user: The admin user.
            reason: Written rejection reason.

        Returns:
            Updated Product.

        Raises:
            ValueError: If reason is empty.
        """
        if not reason.strip():
            raise ValueError("A rejection reason is required.")

        return ProductService._transition(
            product=product,
            new_status=Product.Status.REJECTED,
            actor=admin_user,
            reason=reason,
            extra_fields={"rejection_reason": reason},
        )

    @staticmethod
    @transaction.atomic
    def archive_product(product: Product, actor: Any) -> Product:
        """
        Archive a product — removes it from the marketplace.
        Callable by vendor (own products) or admin.

        Args:
            product: The Product to archive.
            actor: The user performing the action.

        Returns:
            Updated Product.
        """
        return ProductService._transition(
            product=product,
            new_status=Product.Status.ARCHIVED,
            actor=actor,
        )

    # ------------------------------------------------------------------
    # Image management
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def add_image(
        product: Product,
        image_file: Any,
        alt_text: str = "",
    ) -> ProductImage:
        """
        Attach an image to a product.  Position auto-increments.

        Storage is handled by django-storages (S3 / R2 backend).
        Max 8 images per product enforced here.

        Args:
            product: Target Product.
            image_file: Django InMemoryUploadedFile or similar.
            alt_text: Optional accessibility description.

        Returns:
            The new ProductImage instance.

        Raises:
            ValueError: If the product already has 8 images.
        """
        existing_count = product.images.count()
        if existing_count >= 8:
            raise ValueError("A product may have at most 8 images.")

        next_position = existing_count  # 0-indexed
        img = ProductImage.objects.create(
            product=product,
            image=image_file,
            alt_text=alt_text,
            position=next_position,
        )
        logger.info("Image added: product=%s position=%d", product.pk, next_position)
        return img

    @staticmethod
    @transaction.atomic
    def delete_image(image: ProductImage, actor: Any) -> None:
        """
        Remove a product image and reorder remaining images.

        Args:
            image: The ProductImage to delete.
            actor: The user performing the deletion (for audit).
        """
        product = image.product
        position = image.position
        image.delete()

        # Compact positions: shift all images above the deleted one down by 1
        product.images.filter(position__gt=position).update(
            position=models.F("position") - 1
        )
        logger.info("Image deleted: product=%s old_position=%d", product.pk, position)

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def reserve_stock(product: Product, quantity: int) -> InventoryRecord:
        """
        Reserve stock when an order is placed (escrow enters PENDING).

        Uses select_for_update() to prevent concurrent over-reservations.

        Args:
            product: The Product to reserve stock on.
            quantity: Number of units to reserve.

        Returns:
            Updated InventoryRecord.

        Raises:
            InsufficientStockError: If available stock is less than quantity.
        """
        record: InventoryRecord = (
            InventoryRecord.objects.select_for_update()
            .get(product=product)
        )

        if record.track_inventory and not record.allow_backorder:
            if record.quantity_available < quantity:
                raise InsufficientStockError(
                    f"Insufficient stock for '{product.name}'. "
                    f"Available: {record.quantity_available}, requested: {quantity}."
                )

        record.quantity_available = models.F("quantity_available") - quantity
        record.quantity_held = models.F("quantity_held") + quantity
        record.save(update_fields=["quantity_available", "quantity_held", "updated_at"])
        record.refresh_from_db()
        return record

    @staticmethod
    @transaction.atomic
    def release_stock(product: Product, quantity: int) -> InventoryRecord:
        """
        Release held stock back to available (order cancelled / refunded).

        Args:
            product: The Product to release stock on.
            quantity: Number of units to release.

        Returns:
            Updated InventoryRecord.
        """
        record: InventoryRecord = (
            InventoryRecord.objects.select_for_update()
            .get(product=product)
        )
        record.quantity_held = models.F("quantity_held") - quantity
        record.quantity_available = models.F("quantity_available") + quantity
        record.save(update_fields=["quantity_held", "quantity_available", "updated_at"])
        record.refresh_from_db()
        return record

    @staticmethod
    @transaction.atomic
    def deduct_stock(product: Product, quantity: int) -> InventoryRecord:
        """
        Permanently deduct held stock after a successful delivery (RELEASED).

        Args:
            product: The Product.
            quantity: Units to deduct from held stock.

        Returns:
            Updated InventoryRecord.
        """
        record: InventoryRecord = (
            InventoryRecord.objects.select_for_update()
            .get(product=product)
        )
        record.quantity_held = models.F("quantity_held") - quantity
        record.save(update_fields=["quantity_held", "updated_at"])
        record.refresh_from_db()
        return record


# Avoid circular import for models.F usage
from django.db import models  # noqa: E402 — must be after class defs
