"""
apps/products/tests/test_services.py
=====================================
Comprehensive test suite for StoreService and ProductService.

Coverage targets:
    StoreService:
        - register_store (happy path + duplicate guard)
        - approve_store (happy + invalid transition)
        - reject_store (happy + missing reason + invalid transition)
        - suspend_store (happy + listing archival + invalid transition)

    ProductService:
        - create_product (happy + inactive store)
        - submit_for_review
        - approve_product
        - reject_product (with reason)
        - archive_product
        - add_image (happy + 8-image limit)
        - delete_image (gap compaction)
        - reserve_stock (happy + insufficient stock)
        - release_stock
        - deduct_stock
        - concurrent inventory via select_for_update

Run:
    docker compose exec web /opt/venv/bin/pytest apps/products/tests/ -v --tb=short
"""

from __future__ import annotations

import threading
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase

from apps.products.exceptions import (
    InsufficientStockError,
    InvalidProductTransitionError,
    InvalidStoreTransitionError,
    StoreError,
)
from apps.products.models import Category, InventoryRecord, Product, ProductImage, Store
from apps.products.services import ProductService, StoreService

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def _make_user(phone: str, role: str = "VENDOR") -> User:
    """Create a minimal user with a unique phone number."""
    return User.objects.create_user(
        phone_number=phone,
        password="SecurePass123!",
        role=role,
    )


def _make_admin(phone: str = "+260977000001") -> User:
    user = User.objects.create_user(
        phone_number=phone,
        password="AdminPass123!",
        role="ADMIN",
    )
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return user


def _make_category(name: str = "Electronics") -> Category:
    return Category.objects.create(name=name)


def _register_store(owner: User, name: str = "Test Store") -> Store:
    """Register a store using the service layer."""
    return StoreService.register_store(
        owner=owner,
        validated_data={
            "name": name,
            "business_type": Store.BusinessType.INDIVIDUAL,
            "nrc_or_reg_no": "123456/10/1",
            "id_document": SimpleUploadedFile("id.pdf", b"fake", content_type="application/pdf"),
            "business_address": "Plot 1, Cairo Road, Lusaka",
            "phone_number": owner.phone_number,
            "payout_account": "0977000001",
            "payout_provider": Store.PayoutProvider.MTN,
        },
    )


def _approve_store(store: Store, admin: User) -> Store:
    return StoreService.approve_store(store=store, admin_user=admin)


def _make_approved_store(vendor: User, admin: User, name: str = "Test Store") -> Store:
    store = _register_store(vendor, name=name)
    _approve_store(store, admin)
    return store


def _make_product(store: Store, category: Category, name: str = "Fan") -> Product:
    return ProductService.create_product(
        store=store,
        validated_data={
            "name": name,
            "description": "A good fan",
            "category": category,
            "price": Decimal("500.00"),
            "condition": Product.Condition.NEW,
            "initial_quantity": 10,
            "track_inventory": True,
        },
    )


def _fake_image(name: str = "img.jpg") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"\xff\xd8\xff\xe0" + b"\x00" * 100, content_type="image/jpeg")


# ---------------------------------------------------------------------------
# StoreService tests
# ---------------------------------------------------------------------------

class TestStoreServiceRegister(TestCase):

    def setUp(self):
        self.vendor = _make_user("+260977100001")

    def test_register_creates_pending_store(self):
        store = _register_store(self.vendor)
        self.assertEqual(store.status, Store.Status.PENDING)
        self.assertEqual(store.owner, self.vendor)

    def test_register_duplicate_raises(self):
        _register_store(self.vendor)
        with self.assertRaises(StoreError):
            _register_store(self.vendor, name="Second Store")

    def test_register_store_is_not_active(self):
        store = _register_store(self.vendor)
        self.assertFalse(store.is_active)


class TestStoreServiceApprove(TestCase):

    def setUp(self):
        self.vendor = _make_user("+260977100002")
        self.admin = _make_admin("+260977000002")
        self.store = _register_store(self.vendor)

    def test_approve_pending_store(self):
        store = StoreService.approve_store(store=self.store, admin_user=self.admin)
        store.refresh_from_db()
        self.assertEqual(store.status, Store.Status.APPROVED)
        self.assertEqual(store.approved_by, self.admin)
        self.assertIsNotNone(store.approved_at)
        self.assertTrue(store.is_active)

    def test_approve_non_pending_raises(self):
        self.store.status = Store.Status.APPROVED
        self.store.save(update_fields=["status"])
        with self.assertRaises(InvalidStoreTransitionError):
            StoreService.approve_store(store=self.store, admin_user=self.admin)

    def test_approve_logs_to_audit(self):
        from apps.admin_audit.models import AdminAuditLog
        StoreService.approve_store(store=self.store, admin_user=self.admin)
        log = AdminAuditLog.objects.get(action_type="STORE_APPROVED", target_object_id=str(self.store.pk))
        self.assertEqual(log.before_state, {"status": Store.Status.PENDING})
        self.assertEqual(log.after_state, {"status": Store.Status.APPROVED})


class TestStoreServiceReject(TestCase):

    def setUp(self):
        self.vendor = _make_user("+260977100003")
        self.admin = _make_admin("+260977000003")
        self.store = _register_store(self.vendor)

    def test_reject_with_reason(self):
        store = StoreService.reject_store(
            store=self.store, admin_user=self.admin, reason="Invalid ID document."
        )
        store.refresh_from_db()
        self.assertEqual(store.status, Store.Status.REJECTED)
        self.assertEqual(store.rejection_reason, "Invalid ID document.")

    def test_reject_empty_reason_raises(self):
        with self.assertRaises(ValueError):
            StoreService.reject_store(
                store=self.store, admin_user=self.admin, reason="   "
            )

    def test_reject_non_pending_raises(self):
        self.store.status = Store.Status.APPROVED
        self.store.save(update_fields=["status"])
        with self.assertRaises(InvalidStoreTransitionError):
            StoreService.reject_store(
                store=self.store, admin_user=self.admin, reason="Reason."
            )


class TestStoreServiceSuspend(TestCase):

    def setUp(self):
        self.vendor = _make_user("+260977100004")
        self.admin = _make_admin("+260977000004")
        self.store = _make_approved_store(self.vendor, self.admin)
        self.category = _make_category()

    def test_suspend_hides_approved_listings(self):
        # Create an approved product
        p = _make_product(self.store, self.category)
        p.status = Product.Status.APPROVED
        p.save(update_fields=["status"])

        StoreService.suspend_store(
            store=self.store, admin_user=self.admin, reason="Policy violation."
        )
        p.refresh_from_db()
        self.assertEqual(p.status, Product.Status.ARCHIVED)

    def test_suspend_non_approved_raises(self):
        self.store.status = Store.Status.SUSPENDED
        self.store.save(update_fields=["status"])
        with self.assertRaises(InvalidStoreTransitionError):
            StoreService.suspend_store(
                store=self.store, admin_user=self.admin, reason="Reason."
            )

    def test_suspend_empty_reason_raises(self):
        with self.assertRaises(ValueError):
            StoreService.suspend_store(
                store=self.store, admin_user=self.admin, reason=""
            )


# ---------------------------------------------------------------------------
# ProductService tests
# ---------------------------------------------------------------------------

class TestProductServiceCreate(TestCase):

    def setUp(self):
        self.vendor = _make_user("+260977200001")
        self.admin = _make_admin("+260977000005")
        self.store = _make_approved_store(self.vendor, self.admin)
        self.category = _make_category()

    def test_create_product_in_draft(self):
        product = _make_product(self.store, self.category)
        self.assertEqual(product.status, Product.Status.DRAFT)
        self.assertEqual(product.store, self.store)

    def test_create_product_creates_inventory(self):
        product = _make_product(self.store, self.category)
        inv = product.inventory
        self.assertEqual(inv.quantity_available, 10)
        self.assertEqual(inv.quantity_held, 0)

    def test_create_product_inactive_store_raises(self):
        self.store.status = Store.Status.SUSPENDED
        self.store.save(update_fields=["status"])
        with self.assertRaises(StoreError):
            _make_product(self.store, self.category)


class TestProductStateMachine(TestCase):

    def setUp(self):
        self.vendor = _make_user("+260977200002")
        self.admin = _make_admin("+260977000006")
        self.store = _make_approved_store(self.vendor, self.admin)
        self.category = _make_category()
        self.product = _make_product(self.store, self.category)

    def test_draft_to_pending(self):
        ProductService.submit_for_review(self.product, self.vendor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.Status.PENDING)

    def test_pending_to_approved(self):
        self.product.status = Product.Status.PENDING
        self.product.save(update_fields=["status"])
        ProductService.approve_product(self.product, self.admin)
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.Status.APPROVED)
        self.assertIsNotNone(self.product.approved_at)

    def test_pending_to_rejected(self):
        self.product.status = Product.Status.PENDING
        self.product.save(update_fields=["status"])
        ProductService.reject_product(self.product, self.admin, "Counterfeit images.")
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.Status.REJECTED)
        self.assertEqual(self.product.rejection_reason, "Counterfeit images.")

    def test_rejected_to_pending_resubmit(self):
        self.product.status = Product.Status.REJECTED
        self.product.save(update_fields=["status"])
        ProductService.submit_for_review(self.product, self.vendor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.Status.PENDING)

    def test_invalid_transition_raises(self):
        # DRAFT → APPROVED should raise
        with self.assertRaises(InvalidProductTransitionError):
            ProductService.approve_product(self.product, self.admin)

    def test_reject_empty_reason_raises(self):
        self.product.status = Product.Status.PENDING
        self.product.save(update_fields=["status"])
        with self.assertRaises(ValueError):
            ProductService.reject_product(self.product, self.admin, reason="")

    def test_archive_approved_product(self):
        self.product.status = Product.Status.APPROVED
        self.product.save(update_fields=["status"])
        ProductService.archive_product(self.product, self.vendor)
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.Status.ARCHIVED)


class TestProductImageService(TestCase):

    def setUp(self):
        self.vendor = _make_user("+260977200003")
        self.admin = _make_admin("+260977000007")
        self.store = _make_approved_store(self.vendor, self.admin)
        self.category = _make_category()
        self.product = _make_product(self.store, self.category)

    @patch("django.core.files.storage.default_storage.save", return_value="products/images/img.jpg")
    def test_add_image_increments_position(self, _mock_save):
        img1 = ProductService.add_image(self.product, _fake_image("a.jpg"))
        img2 = ProductService.add_image(self.product, _fake_image("b.jpg"))
        self.assertEqual(img1.position, 0)
        self.assertEqual(img2.position, 1)

    @patch("django.core.files.storage.default_storage.save", return_value="products/images/img.jpg")
    def test_add_image_limit_enforced(self, _mock_save):
        for i in range(8):
            ProductImage.objects.create(
                product=self.product,
                image=f"products/images/img{i}.jpg",
                position=i,
            )
        with self.assertRaises(ValueError):
            ProductService.add_image(self.product, _fake_image("extra.jpg"))

    def test_delete_image_compacts_positions(self):
        # Create 3 images directly
        for i in range(3):
            ProductImage.objects.create(
                product=self.product, image=f"img{i}.jpg", position=i
            )
        # Delete middle image (position=1)
        middle = ProductImage.objects.get(product=self.product, position=1)
        ProductService.delete_image(middle, self.vendor)
        positions = list(
            ProductImage.objects.filter(product=self.product)
            .values_list("position", flat=True)
            .order_by("position")
        )
        self.assertEqual(positions, [0, 1])


class TestInventoryService(TestCase):

    def setUp(self):
        self.vendor = _make_user("+260977200004")
        self.admin = _make_admin("+260977000008")
        self.store = _make_approved_store(self.vendor, self.admin)
        self.category = _make_category()
        self.product = _make_product(self.store, self.category)

    def test_reserve_stock_moves_available_to_held(self):
        ProductService.reserve_stock(self.product, quantity=3)
        inv = self.product.inventory
        inv.refresh_from_db()
        self.assertEqual(inv.quantity_available, 7)
        self.assertEqual(inv.quantity_held, 3)

    def test_reserve_stock_insufficient_raises(self):
        with self.assertRaises(InsufficientStockError):
            ProductService.reserve_stock(self.product, quantity=99)

    def test_release_stock_moves_held_to_available(self):
        ProductService.reserve_stock(self.product, quantity=5)
        ProductService.release_stock(self.product, quantity=5)
        inv = self.product.inventory
        inv.refresh_from_db()
        self.assertEqual(inv.quantity_available, 10)
        self.assertEqual(inv.quantity_held, 0)

    def test_deduct_stock_removes_from_held(self):
        ProductService.reserve_stock(self.product, quantity=4)
        ProductService.deduct_stock(self.product, quantity=4)
        inv = self.product.inventory
        inv.refresh_from_db()
        self.assertEqual(inv.quantity_held, 0)
        self.assertEqual(inv.quantity_available, 6)

    def test_no_track_inventory_always_in_stock(self):
        inv = self.product.inventory
        inv.track_inventory = False
        inv.quantity_available = 0
        inv.save()
        self.assertTrue(inv.is_in_stock)

    def test_allow_backorder_allows_zero_stock_reserve(self):
        inv = self.product.inventory
        inv.quantity_available = 0
        inv.allow_backorder = True
        inv.save()
        # Should not raise
        record = ProductService.reserve_stock(self.product, quantity=2)
        self.assertIsNotNone(record)


class TestInventoryConcurrency(TransactionTestCase):
    """
    Verifies that concurrent inventory reservations don't cause overselling.
    select_for_update() must prevent the race.
    """

    def setUp(self):
        self.vendor = _make_user("+260977200005")
        self.admin = _make_admin("+260977000009")
        self.store = _make_approved_store(self.vendor, self.admin)
        self.category = _make_category()
        self.product = _make_product(self.store, self.category)  # qty=10

    def test_concurrent_reserves_do_not_oversell(self):
        errors: list[Exception] = []
        successes: list[bool] = []

        def reserve():
            try:
                ProductService.reserve_stock(self.product, quantity=7)
                successes.append(True)
            except InsufficientStockError:
                successes.append(False)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=reserve) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Unexpected errors: {errors}")
        # Only one reservation of 7 can succeed when stock=10
        self.assertEqual(successes.count(True), 1)

        inv = InventoryRecord.objects.get(product=self.product)
        # Total held must not exceed initial qty
        self.assertLessEqual(inv.quantity_held, 10)
        self.assertGreaterEqual(inv.quantity_available, 0)
