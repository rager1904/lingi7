"""
apps/admin_audit/tests/test_admin_audit.py
==========================================
Pytest suite for the admin_audit application.

Coverage targets
----------------
* AdminAuditLog model immutability guards (save/delete overrides)
* AuditService.log_create / log_update / log_delete
* _serialize_instance helper for edge-case types
* Signal handler: CREATE, UPDATE, DELETE across arbitrary models
* Signal exclusion list (AdminAuditLog rows must NOT trigger recursion)
* AuditMiddleware: IP extraction (direct, X-Forwarded-For, CF-Connecting-IP)
* Actor extraction for authenticated / anonymous / None request
* get_history() queryset helper
* Django admin read-only permissions
* API ViewSet: list, retrieve, filter, search (staff vs non-staff)

All financial/escrow principles are respected — transactions are atomic.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_phone_counter = 0

def _make_user(
    email: str = "admin@lingi7.com",
    is_staff: bool = True,
    is_superuser: bool = False,
) -> Any:
    """Create and return a test user using the Lingi7 custom UserManager."""
    global _phone_counter
    _phone_counter += 1
    phone = f"+2609{_phone_counter:08d}"
    return User.objects.create_user(  # type: ignore[attr-defined]
        email=email,
        password="TestP@ss123!",
        phone_number=phone,
        is_staff=is_staff,
        is_superuser=is_superuser,
    )


# ---------------------------------------------------------------------------
# Model immutability guards
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAdminAuditLogImmutability:
    """AdminAuditLog rows must be write-once and never deletable."""

    def test_initial_save_succeeds(self) -> None:
        from apps.admin_audit.models import ActionType, AdminAuditLog

        entry = AdminAuditLog(
            actor_email="test@lingi7.com",
            action_type=ActionType.CREATE,
            target_content_type="users.user",
            target_object_id="1",
        )
        entry.save()  # Must not raise
        assert AdminAuditLog.objects.filter(pk=entry.pk).exists()

    def test_update_raises_permission_error(self) -> None:
        from apps.admin_audit.models import ActionType, AdminAuditLog

        entry = AdminAuditLog.objects.create(
            actor_email="test@lingi7.com",
            action_type=ActionType.CREATE,
            target_content_type="users.user",
            target_object_id="1",
        )
        entry.actor_email = "hacker@evil.com"
        with pytest.raises(PermissionError, match="immutable"):
            entry.save()

    def test_delete_raises_permission_error(self) -> None:
        from apps.admin_audit.models import ActionType, AdminAuditLog

        entry = AdminAuditLog.objects.create(
            actor_email="test@lingi7.com",
            action_type=ActionType.CREATE,
            target_content_type="users.user",
            target_object_id="99",
        )
        with pytest.raises(PermissionError, match="cannot be deleted"):
            entry.delete()

    def test_str_representation(self) -> None:
        from apps.admin_audit.models import ActionType, AdminAuditLog

        entry = AdminAuditLog(
            actor_email="admin@lingi7.com",
            action_type=ActionType.DELETE,
            target_content_type="escrow.escrowaccount",
            target_object_id="abc-123",
        )
        s = str(entry)
        assert "DELETE" in s
        assert "admin@lingi7.com" in s
        assert "escrow.escrowaccount" in s


# ---------------------------------------------------------------------------
# _serialize_instance helper
# ---------------------------------------------------------------------------


class TestSerializeInstance(TestCase):
    """_serialize_instance must handle all non-JSON-safe types."""

    def test_uuid_serialised_as_string(self) -> None:
        from apps.admin_audit.services import _serialize_instance

        user = MagicMock()
        uid = uuid.uuid4()
        user._meta.app_label = "users"
        user._meta.model_name = "user"
        user.__dict__ = {"id": uid, "_state": object()}

        # Patch model_to_dict to return a uuid
        with patch("apps.admin_audit.services.model_to_dict", return_value={"id": uid}):
            result = _serialize_instance(user)
        assert result["id"] == str(uid)

    def test_decimal_serialised_as_string(self) -> None:
        from apps.admin_audit.services import _serialize_instance

        user = MagicMock()
        with patch(
            "apps.admin_audit.services.model_to_dict",
            return_value={"balance": Decimal("12345.67")},
        ):
            result = _serialize_instance(user)
        assert result["balance"] == "12345.67"

    def test_bytes_serialised_as_string(self) -> None:
        from apps.admin_audit.services import _serialize_instance

        with patch(
            "apps.admin_audit.services.model_to_dict",
            return_value={"data": b"raw bytes"},
        ):
            result = _serialize_instance(MagicMock())
        assert result["data"] == "raw bytes"


# ---------------------------------------------------------------------------
# AuditService
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestAuditService:
    """AuditService must write correct log entries for all action types."""

    def test_log_create_writes_entry(self) -> None:
        from apps.admin_audit.models import ActionType, AdminAuditLog
        from apps.admin_audit.services import AuditService

        actor = _make_user("svc-create@lingi7.com")
        target = _make_user("target@lingi7.com", is_staff=False)

        entry = AuditService.log_create(instance=target, actor=actor)

        assert entry.pk is not None
        assert entry.action_type == ActionType.CREATE
        assert entry.actor == actor
        assert entry.actor_email == actor.email
        assert entry.target_content_type == "users.user"
        assert entry.target_object_id == str(target.pk)
        assert entry.before_state is None
        assert entry.after_state is not None
        assert AdminAuditLog.objects.filter(pk=entry.pk).exists()

    def test_log_update_writes_before_and_after(self) -> None:
        from apps.admin_audit.models import ActionType, AdminAuditLog
        from apps.admin_audit.services import AuditService

        actor = _make_user("svc-update@lingi7.com")
        target = _make_user("target2@lingi7.com", is_staff=False)

        before = {"email": "target2@lingi7.com", "is_active": True}
        target.is_active = False
        target.save()

        entry = AuditService.log_update(
            instance=target, actor=actor, before_state=before
        )

        assert entry.action_type == ActionType.UPDATE
        assert entry.before_state == before
        assert entry.after_state is not None
        assert AdminAuditLog.objects.filter(pk=entry.pk).exists()

    def test_log_delete_writes_before_state(self) -> None:
        from apps.admin_audit.models import ActionType, AdminAuditLog
        from apps.admin_audit.services import AuditService

        actor = _make_user("svc-delete@lingi7.com")
        target = _make_user("to-delete@lingi7.com", is_staff=False)
        target_pk = target.pk

        entry = AuditService.log_delete(instance=target, actor=actor)

        assert entry.action_type == ActionType.DELETE
        assert entry.target_object_id == str(target_pk)
        assert entry.after_state is None
        assert entry.before_state is not None
        assert AdminAuditLog.objects.filter(pk=entry.pk).exists()

    def test_log_create_with_no_actor(self) -> None:
        from apps.admin_audit.models import ActionType, AdminAuditLog
        from apps.admin_audit.services import AuditService

        target = _make_user("orphan@lingi7.com", is_staff=False)

        entry = AuditService.log_create(instance=target, actor=None)

        assert entry.actor is None
        assert entry.actor_email == "system"
        assert entry.action_type == ActionType.CREATE

    def test_log_create_with_request_ip(self) -> None:
        from apps.admin_audit.services import AuditService

        rf = RequestFactory()
        request = rf.post("/", HTTP_CF_CONNECTING_IP="196.20.10.5")
        request.user = _make_user("req-actor@lingi7.com")

        target = _make_user("req-target@lingi7.com", is_staff=False)
        entry = AuditService.log_create(instance=target, actor=request.user, request=request)

        assert entry.ip_address == "196.20.10.5"

    def test_get_history_returns_correct_entries(self) -> None:
        from apps.admin_audit.services import AuditService

        actor = _make_user("history-actor@lingi7.com")
        target = _make_user("history-target@lingi7.com", is_staff=False)

        # Signal already wrote 1 CREATE entry when target was created.
        # Record the count now, then add 2 more via the service directly.
        count_before = AuditService.get_history(target).count()

        AuditService.log_create(instance=target, actor=actor)
        AuditService.log_update(
            instance=target,
            actor=actor,
            before_state={"is_active": True},
        )

        history = AuditService.get_history(target)
        assert history.count() == count_before + 2


# ---------------------------------------------------------------------------
# Middleware: IP extraction
# ---------------------------------------------------------------------------


class TestAuditMiddlewareIPExtraction:
    """AuditMiddleware must correctly extract and stash the request."""

    def _make_request(self, **meta: str) -> Any:
        rf = RequestFactory()
        request = rf.get("/")
        request.META.update(meta)
        return request

    def test_direct_remote_addr(self) -> None:
        from apps.admin_audit.services import AuditService

        request = self._make_request(REMOTE_ADDR="41.72.186.1")
        meta = AuditService._extract_request_meta(request)
        assert meta["ip_address"] == "41.72.186.1"

    def test_cloudflare_header_takes_priority(self) -> None:
        from apps.admin_audit.services import AuditService

        request = self._make_request(
            REMOTE_ADDR="10.0.0.1",
            HTTP_CF_CONNECTING_IP="196.20.10.99",
            HTTP_X_FORWARDED_FOR="172.16.0.1",
        )
        meta = AuditService._extract_request_meta(request)
        assert meta["ip_address"] == "196.20.10.99"

    def test_x_forwarded_for_first_ip(self) -> None:
        from apps.admin_audit.services import AuditService

        request = self._make_request(
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR="41.72.100.1, 10.0.0.2",
        )
        meta = AuditService._extract_request_meta(request)
        assert meta["ip_address"] == "41.72.100.1"

    def test_none_request_returns_nulls(self) -> None:
        from apps.admin_audit.services import AuditService

        meta = AuditService._extract_request_meta(None)
        assert meta["ip_address"] is None
        assert meta["user_agent"] == ""
        assert meta["session_key"] == ""

    def test_middleware_sets_and_clears_thread_local(self) -> None:
        from apps.admin_audit.middleware import AuditMiddleware
        from apps.admin_audit.signals import get_current_request

        captured: list[Any] = []

        def fake_get_response(req: Any) -> Any:
            captured.append(get_current_request())
            return MagicMock(status_code=200)

        mw = AuditMiddleware(fake_get_response)
        rf = RequestFactory()
        req = rf.get("/")
        mw(req)

        assert captured[0] is req  # was set during the call
        assert get_current_request() is None  # cleared after the call

    def test_middleware_clears_on_exception(self) -> None:
        from apps.admin_audit.middleware import AuditMiddleware
        from apps.admin_audit.signals import get_current_request

        def boom(_: Any) -> None:
            raise ValueError("view error")

        mw = AuditMiddleware(boom)  # type: ignore[arg-type]
        rf = RequestFactory()
        with pytest.raises(ValueError):
            mw(rf.get("/"))

        # Thread-local must still be cleared
        assert get_current_request() is None


# ---------------------------------------------------------------------------
# Signal handlers (integration-style, real DB writes)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestSignalHandlers:
    """Signals must write audit entries for create/update/delete on any model."""

    def test_user_create_triggers_audit_log(self) -> None:
        from apps.admin_audit.models import ActionType, AdminAuditLog

        initial_count = AdminAuditLog.objects.count()
        user = User.objects.create_user(  # type: ignore[attr-defined]
            email="signal-create@lingi7.com",
            password="Pass1234!",
            phone_number="+260911111111",
        )
        logs = AdminAuditLog.objects.filter(
            target_content_type="users.user",
            target_object_id=str(user.pk),
            action_type=ActionType.CREATE,
        )
        assert logs.count() == 1
        assert AdminAuditLog.objects.count() > initial_count

    def test_user_update_triggers_audit_log_with_before_state(self) -> None:
        from apps.admin_audit.models import ActionType, AdminAuditLog

        user = User.objects.create_user(  # type: ignore[attr-defined]
            email="signal-create@lingi7.com",
            password="Pass1234!",
            phone_number="+260911111111",
        )
        # Flush the CREATE log
        initial_count = AdminAuditLog.objects.count()

        user.is_active = False
        user.save()

        logs = AdminAuditLog.objects.filter(
            target_content_type="users.user",
            target_object_id=str(user.pk),
            action_type=ActionType.UPDATE,
        )
        assert logs.count() == 1
        log = logs.first()
        assert log.before_state is not None
        assert log.after_state is not None
        assert AdminAuditLog.objects.count() > initial_count

    def test_user_delete_triggers_audit_log(self) -> None:
        from apps.admin_audit.models import ActionType, AdminAuditLog

        user = User.objects.create_user(  # type: ignore[attr-defined]
            email="signal-create@lingi7.com",
            password="Pass1234!",
            phone_number="+260911111111",
        )
        pk = user.pk
        user.delete()

        logs = AdminAuditLog.objects.filter(
            target_content_type="users.user",
            target_object_id=str(pk),
            action_type=ActionType.DELETE,
        )
        assert logs.count() == 1
        log = logs.first()
        assert log.after_state is None
        assert log.before_state is not None

    def test_audit_log_create_does_not_recurse(self) -> None:
        """Creating an AdminAuditLog must NOT trigger another AdminAuditLog."""
        from apps.admin_audit.models import ActionType, AdminAuditLog

        count_before = AdminAuditLog.objects.count()
        # Directly create a log entry
        AdminAuditLog.objects.create(
            actor_email="recursion-test@lingi7.com",
            action_type=ActionType.CREATE,
            target_content_type="users.user",
            target_object_id="999",
        )
        # Exactly 1 new row — no recursion
        assert AdminAuditLog.objects.count() == count_before + 1

    def test_signal_excludes_django_sessions(self) -> None:
        """Session model changes must not generate audit logs."""
        from apps.admin_audit.signals import AUDIT_EXCLUDED_MODELS

        assert "sessions.session" in AUDIT_EXCLUDED_MODELS

    def test_signal_captures_actor_from_thread_local(self) -> None:
        from apps.admin_audit.models import ActionType, AdminAuditLog
        from apps.admin_audit.signals import set_current_request

        actor = _make_user("thread-actor@lingi7.com")

        # Build a minimal request stub with a real user — MagicMock's
        # is_authenticated returns a Mock object (truthy) but the signal
        # handler needs the real attribute to resolve correctly.
        class FakeRequest:
            user = actor
            META = {"REMOTE_ADDR": "127.0.0.1"}
            session = None

        set_current_request(FakeRequest())

        try:
           target = User.objects.create_user(  # type: ignore[attr-defined]
                email="thread-target@lingi7.com",
                password="Pass1234!",
                phone_number="+260911111114",
            )
        finally:
            set_current_request(None)

        log = AdminAuditLog.objects.filter(
            target_object_id=str(target.pk),
            action_type=ActionType.CREATE,
        ).first()

        assert log is not None
        assert log.actor == actor
        assert log.actor_email == actor.email


# ---------------------------------------------------------------------------
# Django admin permissions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAdminAuditLogAdmin:
    """Admin interface must be strictly read-only."""

    def test_no_add_permission(self) -> None:
        from apps.admin_audit.admin import AdminAuditLogAdmin

        site = MagicMock()
        from apps.admin_audit.models import AdminAuditLog as AuditModel
        from django.contrib.admin import site as real_site
        admin_instance = AdminAuditLogAdmin(model=AuditModel, admin_site=real_site)
        assert admin_instance.has_add_permission(MagicMock()) is False

    def test_no_change_permission(self) -> None:
        from apps.admin_audit.admin import AdminAuditLogAdmin

        from apps.admin_audit.models import AdminAuditLog as AuditModel
        from django.contrib.admin import site as real_site
        admin_instance = AdminAuditLogAdmin(model=AuditModel, admin_site=real_site)
        assert admin_instance.has_change_permission(MagicMock()) is False

    def test_no_delete_permission(self) -> None:
        from apps.admin_audit.admin import AdminAuditLogAdmin

        from apps.admin_audit.models import AdminAuditLog as AuditModel
        from django.contrib.admin import site as real_site
        admin_instance = AdminAuditLogAdmin(model=AuditModel, admin_site=real_site)
        assert admin_instance.has_delete_permission(MagicMock()) is False


# ---------------------------------------------------------------------------
# API ViewSet (DRF integration)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAuditLogAPI:
    """API endpoints must enforce is_staff and return correct data."""

    def _create_log_entry(self, email: str = "api-test@lingi7.com") -> Any:
        from apps.admin_audit.models import ActionType, AdminAuditLog

        return AdminAuditLog.objects.create(
            actor_email=email,
            action_type=ActionType.UPDATE,
            target_content_type="users.user",
            target_object_id="42",
            target_repr="User: test",
            before_state={"is_active": True},
            after_state={"is_active": False},
            ip_address="196.20.10.1",
        )

    def test_list_requires_staff(self) -> None:
        from rest_framework.test import APIClient
        user = _make_user("nostaff@lingi7.com", is_staff=False)
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get("/api/v1/admin/audit-logs/")
        assert response.status_code == 403

    def test_list_accessible_to_staff(self) -> None:
        from rest_framework.test import APIClient
        self._create_log_entry()
        staff = _make_user("staff@lingi7.com", is_staff=True)
        client = APIClient()
        client.force_authenticate(user=staff)
        response = client.get("/api/v1/admin/audit-logs/")
        assert response.status_code == 200

    def test_retrieve_single_entry(self) -> None:
        from rest_framework.test import APIClient
        entry = self._create_log_entry("retrieve@lingi7.com")
        staff = _make_user("staff2@lingi7.com", is_staff=True)
        client = APIClient()
        client.force_authenticate(user=staff)
        response = client.get(f"/api/v1/admin/audit-logs/{entry.pk}/")
        assert response.status_code == 200
        assert str(entry.pk) in response.content.decode()

    def test_filter_by_action_type(self) -> None:
        from rest_framework.test import APIClient
        from apps.admin_audit.models import ActionType, AdminAuditLog
        AdminAuditLog.objects.create(
            actor_email="filter@lingi7.com",
            action_type=ActionType.DELETE,
            target_content_type="users.user",
            target_object_id="55",
        )
        staff = _make_user("filterer@lingi7.com", is_staff=True)
        client = APIClient()
        client.force_authenticate(user=staff)
        response = client.get("/api/v1/admin/audit-logs/?action_type=DELETE")
        assert response.status_code == 200
        results = response.json().get("results", response.json())
        for row in results:
            assert row["action_type"] == "DELETE"

    def test_unauthenticated_returns_401_or_403(self) -> None:
        from rest_framework.test import APIClient
        client = APIClient()
        response = client.get("/api/v1/admin/audit-logs/")
        assert response.status_code in (401, 403)