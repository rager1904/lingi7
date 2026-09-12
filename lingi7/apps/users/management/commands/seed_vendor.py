"""
Management command to create a fully-approved VENDOR account for manual testing.

Creates (or upgrades) the vendor User, submits and approves KYC, then
registers and approves their Store so the account can transact immediately.

Idempotent — re-running upgrades an existing account and repairs any
missing KYC/store approval.

Usage:
    python manage.py seed_vendor
    python manage.py seed_vendor --phone +260977786295 --password '!zimRMB@19754' --store-name flavia
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.products.models import Store
from apps.products.services import StoreService
from apps.users.models import KYCStatus, UserRole
from apps.users.services import UserService

User = get_user_model()

logger = logging.getLogger(__name__)

DEFAULT_NRC = "777777/01/1"
DEFAULT_ADDRESS = "123 Freedom Way, Lusaka, Zambia"


class Command(BaseCommand):
    help = (
        "Create a fully-approved VENDOR account (user + KYC + store) for testing."
    )

    def add_arguments(self, parser):
        parser.add_argument("--phone", default="+260977786295")
        parser.add_argument("--password", default="!zimRMB@19754")
        parser.add_argument("--store-name", default="flavia")
        parser.add_argument("--first-name", default="Flavia")
        parser.add_argument("--last-name", default="Vendor")
        parser.add_argument("--admin-phone", default="+260977000001")
        parser.add_argument("--admin-password", default="AdminPass123!")

    def handle(self, *args, **options):
        self._run_tasks_eager()

        phone = options["phone"]
        password = options["password"]
        store_name = options["store_name"]

        admin = self._ensure_admin(options["admin_phone"], options["admin_password"])
        user = self._ensure_vendor(
            phone,
            password,
            options["first_name"],
            options["last_name"],
        )
        self._ensure_kyc_approved(user, admin)
        try:
            store = self._ensure_store_approved(user, store_name, admin)
        except Exception as exc:
            # Data commits are atomic and survive post-commit failures. A
            # notification-dispatch error (e.g. no broker on local dev) must
            # not abort an otherwise-successful seed.
            self.stdout.write(self.style.WARNING(
                f"Store/KYC data committed, but a post-commit notification "
                f"failed ({type(exc).__name__}: {exc}). Ignoring — account is live."
            ))
            store = user.store

        self.stdout.write(self.style.SUCCESS(
            f"Vendor ready: {phone} (password: {password}) | "
            f"KYC={user.kyc_status} | store='{store.name}' ({store.status})"
        ))

    @staticmethod
    def _run_tasks_eager() -> None:
        """Execute Celery notification tasks inline so no broker is required."""
        try:
            from celery import current_app

            current_app.conf.task_always_eager = True
            current_app.conf.task_eager_propagates = False
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not force Celery eager mode: %s", exc)

    def _ensure_admin(self, phone: str, password: str) -> User:
        admin, created = User.objects.get_or_create(
            phone_number=phone,
            defaults={
                "first_name": "Admin",
                "last_name": "Super",
                "role": UserRole.ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "consent_given_at": timezone.now(),
                "phone_verified": True,
                "kyc_status": KYCStatus.VERIFIED,
            },
        )
        if created:
            admin.set_password(password)
            admin.save(update_fields=["password"])
            self.stdout.write(f"  Admin created: {phone}")
        else:
            if not admin.is_staff or not admin.is_superuser:
                admin.is_staff = True
                admin.is_superuser = True
                admin.role = UserRole.ADMIN
                admin.kyc_status = KYCStatus.VERIFIED
                admin.save(
                    update_fields=["is_staff", "is_superuser", "role", "kyc_status"]
                )
            self.stdout.write(f"  Admin ready: {phone}")
        return admin

    def _ensure_vendor(self, phone: str, password: str, first: str, last: str) -> User:
        user, created = User.objects.get_or_create(
            phone_number=phone,
            defaults={
                "first_name": first,
                "last_name": last,
                "role": UserRole.VENDOR,
                "is_active": True,
                "phone_verified": True,
                "consent_given_at": timezone.now(),
            },
        )
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
            self.stdout.write(f"  Vendor created: {phone}")
        else:
            user.role = UserRole.VENDOR
            user.is_active = True
            user.phone_verified = True
            user.set_password(password)
            user.save(update_fields=["role", "is_active", "phone_verified", "password"])
            self.stdout.write(f"  Vendor upgraded: {phone}")
        return user

    def _ensure_kyc_approved(self, user: User, admin: User) -> None:
        if user.kyc_status == KYCStatus.VERIFIED:
            self.stdout.write("  KYC already VERIFIED")
            return

        users = UserService()
        if user.kyc_status in (KYCStatus.UNVERIFIED, KYCStatus.REJECTED):
            uid = str(user.id)
            users.kyc_submit(
                user_id=uid,
                nrc_number=user.nrc_number or DEFAULT_NRC,
                physical_address=user.physical_address or DEFAULT_ADDRESS,
                province=user.province or "Lusaka",
                nrc_front_key=f"kyc/{uid}/front.jpg",
                nrc_back_key=f"kyc/{uid}/back.jpg",
                selfie_key=f"kyc/{uid}/selfie.jpg",
            )
            self.stdout.write("  KYC submitted -> PENDING")

        users.kyc_approve(user_id=str(user.id), reviewed_by=admin)
        self.stdout.write("  KYC approved -> VERIFIED")

    def _ensure_store_approved(self, user: User, store_name: str, admin: User) -> Store:
        if hasattr(user, "store"):
            store = user.store
            self.stdout.write(f"  Store already exists: {store.name} ({store.status})")
        else:
            conflict = Store.objects.filter(name__iexact=store_name).first()
            if conflict and conflict.owner_id != user.id:
                self.stdout.write(self.style.ERROR(
                    f"Store name '{store_name}' is taken by another owner — using it "
                    "anyway would violate uniqueness, aborting."
                ))
                raise SystemExit(1)

            store = StoreService.register_store(
                user,
                {
                    "name": store_name,
                    "description": f"{store_name} store on Lingi7.",
                    "business_type": Store.BusinessType.INDIVIDUAL,
                    "nrc_or_reg_no": user.nrc_number or DEFAULT_NRC,
                    "business_address": user.physical_address or DEFAULT_ADDRESS,
                    "phone_number": user.phone_number,
                },
            )
            self.stdout.write(f"  Store registered: {store.name} ({store.status})")

        if store.status != Store.Status.APPROVED:
            StoreService.approve_store(store, admin)
            self.stdout.write(f"  Store approved: {store.name}")
        else:
            self.stdout.write(f"  Store already APPROVED: {store.name}")
        return store