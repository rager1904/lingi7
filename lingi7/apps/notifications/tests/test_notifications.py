"""
Notifications Test Suite — apps/notifications/tests/test_notifications.py

Tests cover:
  - NotificationLog model creation and state transitions
  - Template rendering for key event types (SMS and email)
  - NotificationService dispatch (SMS and email) with mocked providers
  - Celery task dispatch and retry behaviour
  - Admin read-only enforcement
  - check_failed_notifications monitoring task

Run with:
    docker compose exec web /opt/venv/bin/pytest apps/notifications/tests/ -v --tb=short

Document Ref: LG7-BE-012
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.notifications.models import (
    NotificationChannel,
    NotificationEventType,
    NotificationLog,
    NotificationStatus,
)
from apps.notifications.providers import SendResult
from apps.notifications.services import NotificationService
from apps.notifications.tasks import (
    check_failed_notifications,
    dispatch_order_placed,
    dispatch_payment_success,
    notify_user_task,
    send_email_task,
    send_sms_task,
)
from apps.notifications.templates import NotificationTemplate, TemplateRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def buyer_user(db):
    """Create a buyer user with phone and email."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create_user(
        phone_number="+260971000001",
        password="TestPass123!",
        email="buyer@test.com",
        first_name="Mwamba",
    )


@pytest.fixture
def vendor_user(db):
    """Create a vendor user."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create_user(
        phone_number="+260971000002",
        password="TestPass123!",
        email="vendor@test.com",
        first_name="Chanda",
    )


@pytest.fixture
def mock_sms_success():
    """Patch AT SMS provider to return success."""
    with patch(
        "apps.notifications.services.NotificationService._sms_provider"
    ) as mock:
        mock.send.return_value = SendResult(success=True, provider_ref="AT-MSG-001")
        yield mock


@pytest.fixture
def mock_sms_failure():
    """Patch AT SMS provider to return failure."""
    with patch(
        "apps.notifications.services.NotificationService._sms_provider"
    ) as mock:
        mock.send.return_value = SendResult(success=False, error="Insufficient credit")
        yield mock


@pytest.fixture
def mock_email_success():
    """Patch email provider to return success."""
    with patch(
        "apps.notifications.services.NotificationService._email_provider"
    ) as mock:
        mock.send.return_value = SendResult(success=True, provider_ref="")
        yield mock


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestNotificationLogModel:
    def test_create_log_sms(self, buyer_user):
        log = NotificationLog.objects.create(
            recipient=buyer_user,
            channel=NotificationChannel.SMS,
            event_type=NotificationEventType.ORDER_PLACED,
            recipient_address="+260971000001",
            body_plain="Test SMS body",
            status=NotificationStatus.PENDING,
        )
        assert log.id is not None
        assert log.status == NotificationStatus.PENDING
        assert log.attempt_count == 1

    def test_mark_sent(self, buyer_user):
        log = NotificationLog.objects.create(
            recipient=buyer_user,
            channel=NotificationChannel.SMS,
            event_type=NotificationEventType.ORDER_PLACED,
            recipient_address="+260971000001",
            body_plain="Test",
            status=NotificationStatus.PENDING,
        )
        log.mark_sent(provider_ref="AT-REF-123")
        log.refresh_from_db()
        assert log.status == NotificationStatus.SENT
        assert log.provider_ref == "AT-REF-123"
        assert log.sent_at is not None

    def test_mark_failed(self, buyer_user):
        log = NotificationLog.objects.create(
            recipient=buyer_user,
            channel=NotificationChannel.SMS,
            event_type=NotificationEventType.ORDER_PLACED,
            recipient_address="+260971000001",
            body_plain="Test",
            status=NotificationStatus.PENDING,
        )
        log.mark_failed(error="Provider timeout")
        log.refresh_from_db()
        assert log.status == NotificationStatus.FAILED
        assert log.error_message == "Provider timeout"

    def test_str_representation(self, buyer_user):
        log = NotificationLog.objects.create(
            recipient=buyer_user,
            channel=NotificationChannel.SMS,
            event_type=NotificationEventType.PAYMENT_SUCCESS,
            recipient_address="+260971000001",
            body_plain="Payment received",
            status=NotificationStatus.SENT,
        )
        assert "SMS" in str(log)
        assert "PAYMENT_SUCCESS" in str(log)
        assert "+260971000001" in str(log)


# ---------------------------------------------------------------------------
# Template tests
# ---------------------------------------------------------------------------


class TestTemplateRegistry:
    def test_sms_template_exists_for_all_key_events(self):
        key_events = [
            NotificationEventType.ORDER_PLACED,
            NotificationEventType.PAYMENT_SUCCESS,
            NotificationEventType.ORDER_SHIPPED,
            NotificationEventType.ESCROW_RELEASED,
            NotificationEventType.DISPUTE_OPENED,
            NotificationEventType.STORE_APPROVED,
            NotificationEventType.STORE_REJECTED,
            NotificationEventType.KYC_APPROVED,
            NotificationEventType.LOGIN_OTP,
        ]
        for event in key_events:
            tmpl = TemplateRegistry.get_sms(event)
            assert tmpl is not None, f"No SMS template for {event}"

    def test_email_template_exists_for_key_events(self):
        key_events = [
            NotificationEventType.WELCOME,
            NotificationEventType.PAYMENT_SUCCESS,
            NotificationEventType.ORDER_SHIPPED,
            NotificationEventType.ESCROW_RELEASED,
        ]
        for event in key_events:
            tmpl = TemplateRegistry.get_email(event)
            assert tmpl is not None, f"No email template for {event}"

    def test_sms_template_renders_order_placed(self):
        tmpl = TemplateRegistry.get_sms(NotificationEventType.ORDER_PLACED)
        body = tmpl.render_plain({"order_id": "ORD-001", "amount": "ZMW 1,500"})
        assert "ORD-001" in body
        assert "ZMW 1,500" in body
        assert len(body) <= 320  # max 2 SMS segments

    def test_sms_template_renders_otp(self):
        tmpl = TemplateRegistry.get_sms(NotificationEventType.LOGIN_OTP)
        body = tmpl.render_plain({"otp": "847291"})
        assert "847291" in body
        assert "10 minutes" in body

    def test_email_template_renders_subject(self):
        tmpl = TemplateRegistry.get_email(NotificationEventType.PAYMENT_SUCCESS)
        subject = tmpl.render_subject({"order_id": "ORD-002"})
        assert "ORD-002" in subject

    def test_email_template_renders_html(self):
        tmpl = TemplateRegistry.get_email(NotificationEventType.PAYMENT_SUCCESS)
        html = tmpl.render_html({"order_id": "ORD-002", "amount": "ZMW 2,000"})
        assert "ORD-002" in html
        assert "ZMW 2,000" in html
        assert "escrow" in html.lower()

    def test_welcome_email_contains_lingi7_branding(self):
        tmpl = TemplateRegistry.get_email(NotificationEventType.WELCOME)
        html = tmpl.render_html({"name": "Mwamba"})
        assert "Lingi7" in html
        assert "Mwamba" in html

    def test_template_render_graceful_on_missing_context(self):
        """Template should not raise on missing context keys."""
        tmpl = TemplateRegistry.get_sms(NotificationEventType.ORDER_PLACED)
        # Missing 'order_id' and 'amount' — should fallback gracefully
        body = tmpl.render_plain({})
        assert isinstance(body, str)
        assert len(body) > 0

    def test_unknown_event_returns_none(self):
        assert TemplateRegistry.get_sms("NONEXISTENT_EVENT") is None
        assert TemplateRegistry.get_email("NONEXISTENT_EVENT") is None


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestNotificationService:
    def test_send_sms_success_creates_sent_log(self, buyer_user, mock_sms_success):
        log = NotificationService.send_sms(
            phone_number="+260971000001",
            event_type=NotificationEventType.ORDER_PLACED,
            context={"order_id": "ORD-001", "amount": "ZMW 1,200"},
            recipient=buyer_user,
        )
        assert log is not None
        assert log.status == NotificationStatus.SENT
        assert log.provider_ref == "AT-MSG-001"
        assert log.channel == NotificationChannel.SMS

    def test_send_sms_failure_creates_failed_log(self, buyer_user, mock_sms_failure):
        log = NotificationService.send_sms(
            phone_number="+260971000001",
            event_type=NotificationEventType.ORDER_PLACED,
            context={"order_id": "ORD-002", "amount": "ZMW 500"},
            recipient=buyer_user,
        )
        assert log is not None
        assert log.status == NotificationStatus.FAILED
        assert "Insufficient credit" in log.error_message

    def test_send_email_success_creates_sent_log(self, buyer_user, mock_email_success):
        log = NotificationService.send_email(
            to_address="buyer@test.com",
            event_type=NotificationEventType.PAYMENT_SUCCESS,
            context={"order_id": "ORD-003", "amount": "ZMW 3,000"},
            recipient=buyer_user,
        )
        assert log is not None
        assert log.status == NotificationStatus.SENT
        assert log.channel == NotificationChannel.EMAIL
        assert log.subject  # subject should be populated

    def test_send_sms_unknown_event_returns_none(self, buyer_user):
        log = NotificationService.send_sms(
            phone_number="+260971000001",
            event_type="NONEXISTENT_EVENT",
            context={},
            recipient=buyer_user,
        )
        assert log is None

    def test_notify_user_dispatches_sms_and_email(
        self, buyer_user, mock_sms_success, mock_email_success
    ):
        logs = NotificationService.notify_user(
            user=buyer_user,
            event_type=NotificationEventType.WELCOME,
            context={"name": "Mwamba"},
        )
        channels = {log.channel for log in logs}
        assert NotificationChannel.SMS in channels
        assert NotificationChannel.EMAIL in channels

    def test_notify_user_no_phone_skips_sms(
        self, db, mock_email_success
    ):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        # User with email but no phone
        user = User.objects.create_user(
            phone_number="+260971000099",
            password="pass",
            email="nophone@test.com",
        )
        user.phone_number = ""
        user.save(update_fields=["phone_number"])

        logs = NotificationService.notify_user(
            user=user,
            event_type=NotificationEventType.WELCOME,
            context={"name": "Test"},
            channels=[NotificationChannel.SMS],
        )
        assert len(logs) == 0

    def test_log_stores_context_data(self, buyer_user, mock_sms_success):
        ctx = {"order_id": "ORD-999", "amount": "ZMW 5,000"}
        log = NotificationService.send_sms(
            phone_number="+260971000001",
            event_type=NotificationEventType.ORDER_PLACED,
            context=ctx,
            recipient=buyer_user,
        )
        assert log.context_data == ctx

    def test_log_stores_related_object(self, buyer_user, mock_sms_success):
        log = NotificationService.send_sms(
            phone_number="+260971000001",
            event_type=NotificationEventType.ORDER_PLACED,
            context={"order_id": "ORD-888", "amount": "ZMW 800"},
            recipient=buyer_user,
            related_object_id="888",
            related_object_type="orders.Order",
        )
        assert log.related_object_id == "888"
        assert log.related_object_type == "orders.Order"

    def test_provider_exception_does_not_raise_to_caller(self, buyer_user):
        """Notification failures must never propagate to the calling transaction."""
        with patch(
            "apps.notifications.services.NotificationService._sms_provider"
        ) as mock:
            mock.send.side_effect = RuntimeError("Unexpected crash")
            # Must NOT raise
            log = NotificationService.send_sms(
                phone_number="+260971000001",
                event_type=NotificationEventType.ORDER_PLACED,
                context={"order_id": "ORD-ERR", "amount": "ZMW 100"},
                recipient=buyer_user,
            )
            assert log is not None
            assert log.status == NotificationStatus.FAILED


# ---------------------------------------------------------------------------
# Celery task tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestNotificationTasks:
    def test_send_sms_task_returns_log_uuid(self, buyer_user, mock_sms_success):
        result = send_sms_task(
            phone_number="+260971000001",
            event_type=NotificationEventType.PAYMENT_SUCCESS,
            context={"order_id": "ORD-T01", "amount": "ZMW 1,000"},
            user_pk=buyer_user.pk,
        )
        assert result is not None
        # Validate it's a UUID string
        uuid.UUID(result)

    def test_send_email_task_returns_log_uuid(self, buyer_user, mock_email_success):
        result = send_email_task(
            to_address="buyer@test.com",
            event_type=NotificationEventType.PAYMENT_SUCCESS,
            context={"order_id": "ORD-T02", "amount": "ZMW 2,000"},
            user_pk=buyer_user.pk,
        )
        assert result is not None
        uuid.UUID(result)

    def test_notify_user_task_returns_list_of_uuids(
        self, buyer_user, mock_sms_success, mock_email_success
    ):
        results = notify_user_task(
            user_pk=buyer_user.pk,
            event_type=NotificationEventType.WELCOME,
            context={"name": "Mwamba"},
        )
        assert isinstance(results, list)
        assert len(results) >= 1
        for r in results:
            uuid.UUID(r)

    def test_notify_user_task_invalid_user_returns_empty(self, db):
        results = notify_user_task(
            user_pk=999999,
            event_type=NotificationEventType.WELCOME,
            context={},
        )
        assert results == []

    def test_dispatch_order_placed_queues_task(self, buyer_user):
        with patch("apps.notifications.tasks.notify_user_task") as mock_task:
            dispatch_order_placed(
                buyer_user_pk=buyer_user.pk,
                order_id="ORD-D01",
                amount_display="ZMW 750",
            )
            mock_task.delay.assert_called_once()
            call_kwargs = mock_task.delay.call_args[1]
            assert call_kwargs["event_type"] == NotificationEventType.ORDER_PLACED
            assert call_kwargs["context"]["order_id"] == "ORD-D01"

    def test_dispatch_payment_success_queues_task(self, buyer_user):
        with patch("apps.notifications.tasks.notify_user_task") as mock_task:
            dispatch_payment_success(
                buyer_user_pk=buyer_user.pk,
                order_id="ORD-D02",
                amount_display="ZMW 1,800",
            )
            mock_task.delay.assert_called_once()


# ---------------------------------------------------------------------------
# Monitoring task tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMonitoringTask:
    def test_check_failed_notifications_returns_dict(self, buyer_user):
        # Create some FAILED logs
        for _ in range(3):
            NotificationLog.objects.create(
                recipient=buyer_user,
                channel=NotificationChannel.SMS,
                event_type=NotificationEventType.ORDER_PLACED,
                recipient_address="+260971000001",
                body_plain="Test",
                status=NotificationStatus.FAILED,
            )

        result = check_failed_notifications()
        assert isinstance(result, dict)
        assert "SMS" in result
        assert "EMAIL" in result
        assert result["SMS"] >= 3

    def test_check_failed_no_failures_returns_zeros(self, db):
        result = check_failed_notifications()
        assert all(v == 0 for v in result.values())


# ---------------------------------------------------------------------------
# Admin tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestNotificationAdmin:
    def test_admin_no_add_permission(self, buyer_user):
        from apps.notifications.admin import NotificationLogAdmin
        from django.contrib.admin import site

        admin_obj = NotificationLogAdmin(NotificationLog, site)
        mock_request = MagicMock()
        mock_request.user = buyer_user
        assert admin_obj.has_add_permission(mock_request) is False

    def test_admin_no_change_permission(self, buyer_user):
        from apps.notifications.admin import NotificationLogAdmin
        from django.contrib.admin import site

        admin_obj = NotificationLogAdmin(NotificationLog, site)
        mock_request = MagicMock()
        assert admin_obj.has_change_permission(mock_request) is False

    def test_admin_no_delete_permission(self, buyer_user):
        from apps.notifications.admin import NotificationLogAdmin
        from django.contrib.admin import site

        admin_obj = NotificationLogAdmin(NotificationLog, site)
        mock_request = MagicMock()
        assert admin_obj.has_delete_permission(mock_request) is False
