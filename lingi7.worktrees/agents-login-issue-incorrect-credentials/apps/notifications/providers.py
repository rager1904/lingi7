"""
Notification Providers — apps/notifications/providers.py

Thin client wrappers for each transport channel.

Africa's Talking is the recommended SMS gateway for Zambia: it has
direct operator connections to MTN Zambia and Airtel Zambia and supports
both the ZMW-based pricing and ZM shortcodes.

For email, AWS SES is the primary provider (configured via boto3).
Django's built-in SMTP backend is used as fallback in dev/test.

No business logic lives here. Each provider raises NotificationSendError
on failure — the service layer handles retry decisions.

Document Ref: LG7-BE-012
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


class NotificationSendError(Exception):
    """Raised when a provider fails to accept a message."""

    pass


@dataclass
class SendResult:
    """Return type from all provider send methods.

    Attributes:
        success:      True if the provider accepted the message.
        provider_ref: Provider-assigned message ID. Empty on failure.
        error:        Error description. Empty on success.
    """

    success: bool
    provider_ref: str = ""
    error: str = ""


class AfricasTalkingSMSProvider:
    """
    SMS provider using Africa's Talking API.

    Africa's Talking (africastalking.com) provides direct carrier
    connections to MTN Zambia and Airtel Zambia with Zambian shortcode
    support. Credentials are read from Django settings:

        AT_USERNAME:   Africa's Talking username (use 'sandbox' for dev)
        AT_API_KEY:    API key from AT dashboard
        AT_SENDER_ID:  Registered shortcode or sender ID (e.g. 'LINGI7')

    Falls back to a console logger in DEBUG mode so tests and local dev
    do not require live AT credentials.
    """

    def __init__(self) -> None:
        self.username: str = getattr(settings, "AT_USERNAME", "sandbox")
        self.api_key: str = getattr(settings, "AT_API_KEY", "")
        self.sender_id: str = getattr(settings, "AT_SENDER_ID", "LINGI7")
        self.debug_mode: bool = getattr(settings, "NOTIFICATIONS_DEBUG_MODE", settings.DEBUG)

    def send(self, phone_number: str, message: str) -> SendResult:
        """Send an SMS via Africa's Talking.

        Args:
            phone_number: E.164 format, e.g. +260971234567
            message:      Plain text body (max 160 chars for single SMS).

        Returns:
            SendResult with provider ref on success.

        Raises:
            NotificationSendError: On provider-level failure after
                the call returns — the caller decides on retry.
        """
        if self.debug_mode:
            logger.info(
                "[AT-SMS DEBUG] To: %s | Sender: %s | Body: %s",
                phone_number,
                self.sender_id,
                message,
            )
            return SendResult(success=True, provider_ref="DEBUG-SMS-REF")

        try:
            import africastalking  # type: ignore[import]

            africastalking.initialize(self.username, self.api_key)
            sms = africastalking.SMS
            response = sms.send(
                message,
                [phone_number],
                sender_id=self.sender_id,
            )
            recipients = response.get("SMSMessageData", {}).get("Recipients", [])
            if not recipients:
                return SendResult(success=False, error="AT returned no recipients")

            recipient = recipients[0]
            status_code = recipient.get("statusCode", 0)

            if status_code == 101:
                return SendResult(
                    success=True,
                    provider_ref=recipient.get("messageId", ""),
                )
            else:
                error = recipient.get("status", "Unknown AT error")
                logger.warning("AT SMS failed for %s: %s", phone_number, error)
                return SendResult(success=False, error=error)

        except ImportError:
            msg = (
                "africastalking package not installed. "
                "Add africastalking to requirements/base.txt"
            )
            logger.error(msg)
            return SendResult(success=False, error=msg)
        except Exception as exc:
            logger.exception("Unexpected AT SMS error for %s", phone_number)
            return SendResult(success=False, error=str(exc))


class DjangoEmailProvider:
    """
    Email provider using Django's email backend.

    In production, configure Django's EMAIL_BACKEND to use AWS SES:
        EMAIL_BACKEND = 'django_ses.SESBackend'

    In development/test, the console backend is used automatically
    via Django settings (no code changes needed here).

    Sends both plain-text and HTML alternatives in a single message.
    """

    def __init__(self) -> None:
        self.from_address: str = getattr(
            settings, "DEFAULT_FROM_EMAIL", "noreply@lingi7.com"
        )

    def send(
        self,
        to_address: str,
        subject: str,
        body_plain: str,
        body_html: Optional[str] = None,
    ) -> SendResult:
        """Send an email via the configured Django email backend.

        Args:
            to_address:  Recipient email address.
            subject:     Email subject line.
            body_plain:  Plain-text fallback body.
            body_html:   Optional HTML body. Attached as alternative.

        Returns:
            SendResult with empty provider_ref (SES ref comes via SNS).
        """
        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=body_plain,
                from_email=self.from_address,
                to=[to_address],
            )
            if body_html:
                msg.attach_alternative(body_html, "text/html")

            sent_count = msg.send(fail_silently=False)

            if sent_count > 0:
                logger.info("Email sent to %s: %s", to_address, subject)
                return SendResult(success=True, provider_ref="")
            else:
                return SendResult(success=False, error="Django email backend returned 0")

        except Exception as exc:
            logger.exception("Email send failed to %s", to_address)
            return SendResult(success=False, error=str(exc))
