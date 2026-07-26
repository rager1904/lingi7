"""
Notification Service — apps/notifications/services.py

NotificationService is the sole entry point for dispatching notifications.
No view, task, or signal should call a provider directly — always go through
this service.

Responsibilities:
  - Resolve recipient address from user model
  - Render the correct template for the event type
  - Create a NotificationLog row (PENDING)
  - Hand off to the appropriate provider
  - Update log row to SENT or FAILED
  - Never raise to caller on provider failure — log and continue

Retry logic lives in Celery tasks, not here. The service is synchronous
and idempotent — safe to call from both sync views and async Celery tasks.

Document Ref: LG7-BE-012
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import (
    NotificationChannel,
    NotificationEventType,
    NotificationLog,
    NotificationStatus,
)
from .providers import AfricasTalkingSMSProvider, DjangoEmailProvider
from .templates import NotificationTemplate, TemplateRegistry

logger = logging.getLogger(__name__)

User = get_user_model()


class NotificationService:
    """
    Central dispatcher for all platform notifications.

    Usage:
        # Fire-and-forget — always call this, never providers directly.
        NotificationService.send_sms(
            phone_number="+260971234567",
            event_type=NotificationEventType.ORDER_PLACED,
            context={"order_id": "ORD-001", "amount": "ZMW 1,200"},
            recipient=user_instance,
            related_object_id=str(order.pk),
            related_object_type="orders.Order",
        )

        NotificationService.send_email(
            to_address="buyer@example.com",
            event_type=NotificationEventType.PAYMENT_RECEIPT,
            context={"buyer_name": "Mwamba", "amount": "ZMW 2,500"},
            recipient=user_instance,
        )

    All methods return the created NotificationLog instance.
    Failures are logged but never raised — notifications must never
    break the calling transaction.
    """

    _sms_provider: AfricasTalkingSMSProvider = AfricasTalkingSMSProvider()
    _email_provider: DjangoEmailProvider = DjangoEmailProvider()

    @classmethod
    def send_sms(
        cls,
        phone_number: str,
        event_type: str,
        context: Optional[dict[str, Any]] = None,
        recipient: Optional[Any] = None,
        related_object_id: str = "",
        related_object_type: str = "",
    ) -> Optional[NotificationLog]:
        """Dispatch an SMS notification.

        Renders the SMS template for the given event_type, creates a
        NotificationLog, and sends via Africa's Talking.

        Args:
            phone_number:        E.164 recipient phone number.
            event_type:          NotificationEventType constant.
            context:             Template variable dict. Merged with defaults.
            recipient:           Optional User FK for the log record.
            related_object_id:   PK of triggering domain object.
            related_object_type: Django app.Model label for above.

        Returns:
            The created NotificationLog, or None if template lookup fails.
        """
        if context is None:
            context = {}

        template: Optional[NotificationTemplate] = TemplateRegistry.get_sms(event_type)
        if template is None:
            logger.error(
                "No SMS template registered for event_type=%s", event_type
            )
            return None

        body = template.render_plain(context)

        log = NotificationLog.objects.create(
            recipient=recipient,
            channel=NotificationChannel.SMS,
            event_type=event_type,
            recipient_address=phone_number,
            subject="",
            body_plain=body,
            status=NotificationStatus.PENDING,
            context_data=context,
            related_object_id=related_object_id,
            related_object_type=related_object_type,
        )

        try:
            result = cls._sms_provider.send(phone_number=phone_number, message=body)
            if result.success:
                log.mark_sent(provider_ref=result.provider_ref)
                logger.info(
                    "SMS sent | event=%s | to=%s | ref=%s",
                    event_type,
                    phone_number,
                    result.provider_ref,
                )
            else:
                log.mark_failed(error=result.error)
                logger.warning(
                    "SMS failed | event=%s | to=%s | error=%s",
                    event_type,
                    phone_number,
                    result.error,
                )
        except Exception as exc:
            log.mark_failed(error=str(exc))
            logger.exception(
                "Unexpected SMS error | event=%s | to=%s", event_type, phone_number
            )

        return log

    @classmethod
    def send_email(
        cls,
        to_address: str,
        event_type: str,
        context: Optional[dict[str, Any]] = None,
        recipient: Optional[Any] = None,
        related_object_id: str = "",
        related_object_type: str = "",
    ) -> Optional[NotificationLog]:
        """Dispatch an email notification.

        Renders both plain-text and HTML templates for the given event_type,
        creates a NotificationLog, and sends via the configured email backend.

        Args:
            to_address:          Recipient email address.
            event_type:          NotificationEventType constant.
            context:             Template variable dict.
            recipient:           Optional User FK for the log record.
            related_object_id:   PK of triggering domain object.
            related_object_type: Django app.Model label for above.

        Returns:
            The created NotificationLog, or None if template lookup fails.
        """
        if context is None:
            context = {}

        template: Optional[NotificationTemplate] = TemplateRegistry.get_email(
            event_type
        )
        if template is None:
            logger.error(
                "No email template registered for event_type=%s", event_type
            )
            return None

        subject = template.render_subject(context)
        body_plain = template.render_plain(context)
        body_html = template.render_html(context)

        log = NotificationLog.objects.create(
            recipient=recipient,
            channel=NotificationChannel.EMAIL,
            event_type=event_type,
            recipient_address=to_address,
            subject=subject,
            body_plain=body_plain,
            body_html=body_html,
            status=NotificationStatus.PENDING,
            context_data=context,
            related_object_id=related_object_id,
            related_object_type=related_object_type,
        )

        try:
            result = cls._email_provider.send(
                to_address=to_address,
                subject=subject,
                body_plain=body_plain,
                body_html=body_html if body_html else None,
            )
            if result.success:
                log.mark_sent(provider_ref=result.provider_ref)
                logger.info(
                    "Email sent | event=%s | to=%s | subject=%s",
                    event_type,
                    to_address,
                    subject,
                )
            else:
                log.mark_failed(error=result.error)
                logger.warning(
                    "Email failed | event=%s | to=%s | error=%s",
                    event_type,
                    to_address,
                    result.error,
                )
        except Exception as exc:
            log.mark_failed(error=str(exc))
            logger.exception(
                "Unexpected email error | event=%s | to=%s", event_type, to_address
            )

        return log

    @classmethod
    def notify_user(
        cls,
        user: Any,
        event_type: str,
        context: Optional[dict[str, Any]] = None,
        channels: Optional[list[str]] = None,
        related_object_id: str = "",
        related_object_type: str = "",
    ) -> list[NotificationLog]:
        """Convenience: dispatch a notification across multiple channels for a user.

        Resolves addresses from the user model. Sends to all specified channels.
        If channels is None, defaults to SMS (always) + EMAIL (if user has email).

        Args:
            user:                User model instance.
            event_type:          NotificationEventType constant.
            context:             Template variable dict.
            channels:            List of NotificationChannel values.
                                 Defaults to [SMS] or [SMS, EMAIL] based on user.
            related_object_id:   PK of triggering domain object.
            related_object_type: Django app.Model label for above.

        Returns:
            List of created NotificationLog instances (one per channel sent).
        """
        if context is None:
            context = {}

        logs: list[NotificationLog] = []

        if channels is None:
            channels = [NotificationChannel.SMS]
            if getattr(user, "email", None):
                channels.append(NotificationChannel.EMAIL)

        kwargs = dict(
            event_type=event_type,
            context=context,
            recipient=user,
            related_object_id=related_object_id,
            related_object_type=related_object_type,
        )

        for channel in channels:
            if channel == NotificationChannel.SMS:
                phone = getattr(user, "phone_number", None)
                if phone:
                    log = cls.send_sms(phone_number=phone, **kwargs)
                    if log:
                        logs.append(log)
                else:
                    logger.warning(
                        "SMS requested but user %s has no phone_number", user.pk
                    )

            elif channel == NotificationChannel.EMAIL:
                email = getattr(user, "email", None)
                if email:
                    log = cls.send_email(to_address=email, **kwargs)
                    if log:
                        logs.append(log)
                else:
                    logger.warning(
                        "EMAIL requested but user %s has no email", user.pk
                    )

        return logs
