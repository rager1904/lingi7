"""
Notification Templates — apps/notifications/templates.py

All notification content lives here. Each event type has a registered
template that renders subject, plain-text body, and optional HTML body.

Design rationale:
  - Templates are pure Python string formatting (no Django template engine)
    so they work in Celery workers without a request context.
  - HTML templates are minimal — transactional email, not marketing.
  - SMS templates are <= 160 chars for single-segment delivery.
  - All amounts are pre-formatted before passing to templates
    (use format_zmw() helper in callers).

To add a new event:
  1. Add the event to NotificationEventType in models.py
  2. Register SMS and/or email templates in TemplateRegistry below.

Document Ref: LG7-BE-012
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from html import escape as _esc
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template dataclass
# ---------------------------------------------------------------------------


@dataclass
class NotificationTemplate:
    """Holds rendering callables for one notification event.

    Attributes:
        event_type:      The NotificationEventType key this template handles.
        subject_fn:      Callable(context) -> subject str. Empty for SMS.
        plain_fn:        Callable(context) -> plain text body.
        html_fn:         Optional callable(context) -> HTML body for email.
    """

    event_type: str
    plain_fn: Callable[[dict], str]
    subject_fn: Callable[[dict], str] = field(
        default_factory=lambda: lambda ctx: ""
    )
    html_fn: Optional[Callable[[dict], str]] = None

    def render_subject(self, context: dict) -> str:
        """Render the email subject line."""
        try:
            return self.subject_fn(context)
        except (KeyError, TypeError) as exc:
            logger.error("Template subject render error for %s: %s", self.event_type, exc)
            return f"Lingi7 Notification — {self.event_type}"

    def render_plain(self, context: dict) -> str:
        """Render the plain-text body."""
        try:
            return self.plain_fn(context)
        except (KeyError, TypeError) as exc:
            logger.error("Template plain render error for %s: %s", self.event_type, exc)
            return "You have a new notification from Lingi7. Please log in for details."

    def render_html(self, context: dict) -> str:
        """Render the HTML body. Falls back to plain if no html_fn."""
        if self.html_fn is None:
            return ""
        try:
            return self.html_fn(context)
        except (KeyError, TypeError) as exc:
            logger.error("Template HTML render error for %s: %s", self.event_type, exc)
            return ""


# ---------------------------------------------------------------------------
# HTML email wrapper — minimal transactional template
# ---------------------------------------------------------------------------

_PLATFORM_URL = "https://lingi7.com"
_SUPPORT_EMAIL = "support@lingi7.com"


def _html_wrap(title: str, body_html: str) -> str:
    """Wrap content in a minimal responsive HTML email shell."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    body {{ font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }}
    .container {{ max-width: 600px; margin: 0 auto; background: #ffffff;
                 border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
    .header {{ background: #0D2137; padding: 24px 32px; }}
    .header h1 {{ color: #ffffff; margin: 0; font-size: 22px; font-weight: bold; }}
    .header span {{ color: #F5A623; }}
    .body {{ padding: 32px; color: #333333; line-height: 1.6; }}
    .body h2 {{ color: #0D2137; font-size: 18px; margin-top: 0; }}
    .highlight-box {{ background: #F0F7FF; border-left: 4px solid #0D2137;
                      padding: 16px; border-radius: 4px; margin: 16px 0; }}
    .amount {{ font-size: 24px; font-weight: bold; color: #0D2137; }}
    .cta-button {{ display: inline-block; background: #F5A623; color: #0D2137;
                   padding: 12px 24px; border-radius: 6px; text-decoration: none;
                   font-weight: bold; margin: 16px 0; }}
    .footer {{ background: #f5f5f5; padding: 16px 32px; font-size: 12px; color: #888888; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>Lingi<span>7</span></h1>
    </div>
    <div class="body">
      {body_html}
    </div>
    <div class="footer">
      <p>This email was sent by Lingi7 &mdash; Zambia&apos;s trusted escrow marketplace.</p>
      <p>Questions? Email <a href="mailto:{_SUPPORT_EMAIL}">{_SUPPORT_EMAIL}</a></p>
      <p>AfriCore Intelligence Limited &bull; Lusaka, Zambia</p>
    </div>
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------


def _t_welcome_plain(ctx: dict) -> str:
    name = ctx.get("name", "there")
    return (
        f"Welcome to Lingi7, {name}! Your account is ready. "
        f"Shop with confidence — every purchase is protected by escrow. "
        f"Visit {_PLATFORM_URL} to get started."
    )


def _t_welcome_html(ctx: dict) -> str:
    name = _esc(ctx.get("name", "there"))
    return _html_wrap(
        "Welcome to Lingi7",
        f"""<h2>Welcome to Lingi7, {name}!</h2>
        <p>Your account has been created successfully.</p>
        <div class="highlight-box">
          <strong>Every purchase is protected by escrow.</strong><br>
          Your money is held safely until you confirm delivery.
        </div>
        <a href="{_PLATFORM_URL}" class="cta-button">Start Shopping</a>""",
    )


def _t_payment_success_plain(ctx: dict) -> str:
    amount = ctx.get("amount", "")
    order_id = ctx.get("order_id", "")
    return (
        f"Lingi7: Payment of {amount} received for Order #{order_id}. "
        f"Your funds are held in escrow. The seller has been notified to ship."
    )


def _t_payment_success_html(ctx: dict) -> str:
    amount = _esc(ctx.get("amount", ""))
    order_id = _esc(ctx.get("order_id", ""))
    seller = _esc(ctx.get("seller_name", "the seller"))
    return _html_wrap(
        "Payment Successful",
        f"""<h2>Payment Successful</h2>
        <div class="highlight-box">
          <div class="amount">{amount}</div>
          <p>Order #{order_id} &bull; Held in Escrow</p>
        </div>
        <p>Your payment has been received and securely held in escrow.
           {seller} has been notified to prepare your order for shipment.</p>
        <p>Your money will only be released to the seller once
           <strong>you confirm delivery</strong>.</p>
        <a href="{_PLATFORM_URL}/orders/{order_id}" class="cta-button">Track Order</a>""",
    )


def _t_payment_failed_plain(ctx: dict) -> str:
    order_id = ctx.get("order_id", "")
    reason = ctx.get("reason", "Please try again or use a different method.")
    return (
        f"Lingi7: Payment for Order #{order_id} was not successful. "
        f"{reason} Visit {_PLATFORM_URL} to retry."
    )


def _t_order_placed_plain(ctx: dict) -> str:
    order_id = ctx.get("order_id", "")
    amount = ctx.get("amount", "")
    return (
        f"Lingi7: Order #{order_id} placed for {amount}. "
        f"Complete payment to confirm. Reply HELP for assistance."
    )


def _t_order_shipped_plain(ctx: dict) -> str:
    order_id = ctx.get("order_id", "")
    tracking = ctx.get("tracking_number", "")
    carrier = ctx.get("carrier", "the carrier")
    return (
        f"Lingi7: Your order #{order_id} has been shipped by {carrier}. "
        f"Tracking: {tracking}. Track at {_PLATFORM_URL}/track/{tracking}"
    )


def _t_order_shipped_html(ctx: dict) -> str:
    order_id = _esc(ctx.get("order_id", ""))
    tracking = _esc(ctx.get("tracking_number", ""))
    carrier = _esc(ctx.get("carrier", "the seller"))
    return _html_wrap(
        "Your Order Has Shipped",
        f"""<h2>Your Order Is On Its Way!</h2>
        <div class="highlight-box">
          <strong>Order #{order_id}</strong><br>
          Carrier: {carrier}<br>
          Tracking: <strong>{tracking}</strong>
        </div>
        <p>Your order has been dispatched. Once you receive and confirm delivery,
           the escrowed funds will be released to the seller.</p>
        <a href="{_PLATFORM_URL}/track/{tracking}" class="cta-button">Track Shipment</a>""",
    )


def _t_order_delivered_plain(ctx: dict) -> str:
    order_id = ctx.get("order_id", "")
    timeout_days = ctx.get("auto_confirm_days", 7)
    return (
        f"Lingi7: Order #{order_id} has been marked as delivered. "
        f"Please confirm receipt within {timeout_days} days or it will be auto-confirmed. "
        f"Visit {_PLATFORM_URL}/orders/{order_id}"
    )


def _t_escrow_released_plain(ctx: dict) -> str:
    order_id = ctx.get("order_id", "")
    amount = ctx.get("amount", "")
    account = ctx.get("payout_account", "your registered account")
    return (
        f"Lingi7: Escrow released. {amount} for Order #{order_id} "
        f"has been sent to {account}. Thank you for selling on Lingi7!"
    )


def _t_escrow_released_html(ctx: dict) -> str:
    order_id = _esc(ctx.get("order_id", ""))
    amount = _esc(ctx.get("amount", ""))
    account = _esc(ctx.get("payout_account", "your registered account"))
    return _html_wrap(
        "Payout Sent",
        f"""<h2>Your Payout Has Been Sent!</h2>
        <div class="highlight-box">
          <div class="amount">{amount}</div>
          <p>Order #{order_id} &bull; Sent to {account}</p>
        </div>
        <p>The buyer has confirmed delivery. The escrowed funds have been
           released and disbursed to your registered Mobile Money account.</p>
        <a href="{_PLATFORM_URL}/vendor/payouts" class="cta-button">View Payout History</a>""",
    )


def _t_dispute_opened_plain(ctx: dict) -> str:
    order_id = ctx.get("order_id", "")
    return (
        f"Lingi7: A dispute has been opened for Order #{order_id}. "
        f"Funds are frozen until resolution. Our team will contact you within 48 hours. "
        f"Visit {_PLATFORM_URL}/disputes for details."
    )


def _t_dispute_resolved_plain(ctx: dict) -> str:
    order_id = ctx.get("order_id", "")
    outcome = ctx.get("outcome", "resolved")
    return (
        f"Lingi7: Dispute for Order #{order_id} has been {outcome}. "
        f"Please log in to view the resolution details and any refund status."
    )


def _t_escrow_frozen_plain(ctx: dict) -> str:
    order_id = ctx.get("order_id", "")
    return (
        f"Lingi7: Order #{order_id} has been flagged for review. "
        f"Funds are frozen pending manual verification. "
        f"Our team will review within 24 hours. Contact support@lingi7.com if urgent."
    )


def _t_store_approved_plain(ctx: dict) -> str:
    store_name = ctx.get("store_name", "Your store")
    return (
        f"Lingi7: Congratulations! {store_name} has been approved and is now live. "
        f"You can now add products at {_PLATFORM_URL}/vendor/dashboard"
    )


def _t_store_rejected_plain(ctx: dict) -> str:
    store_name = ctx.get("store_name", "Your store")
    reason = ctx.get("reason", "your application did not meet our requirements")
    return (
        f"Lingi7: {store_name} application was not approved. "
        f"Reason: {reason}. "
        f"Please contact {_SUPPORT_EMAIL} to reapply."
    )


def _t_store_suspended_plain(ctx: dict) -> str:
    store_name = ctx.get("store_name", "Your store")
    return (
        f"Lingi7: {store_name} has been suspended. "
        f"All listings are temporarily hidden. "
        f"Contact {_SUPPORT_EMAIL} for more information."
    )


def _t_listing_approved_plain(ctx: dict) -> str:
    product_name = ctx.get("product_name", "Your product")
    return (
        f"Lingi7: '{product_name}' has been approved and is now visible to buyers. "
        f"View it at {_PLATFORM_URL}/vendor/products"
    )


def _t_listing_rejected_plain(ctx: dict) -> str:
    product_name = ctx.get("product_name", "Your product")
    reason = ctx.get("reason", "it did not meet our listing guidelines")
    return (
        f"Lingi7: '{product_name}' was not approved. "
        f"Reason: {reason}. Please update and resubmit."
    )


def _t_kyc_approved_plain(ctx: dict) -> str:
    name = ctx.get("name", "there")
    return (
        f"Lingi7: Hi {name}, your identity has been verified. "
        f"You can now access all platform features. Welcome aboard!"
    )


def _t_kyc_rejected_plain(ctx: dict) -> str:
    reason = ctx.get("reason", "the documents provided were insufficient")
    return (
        f"Lingi7: Your KYC verification was not approved. "
        f"Reason: {reason}. "
        f"Please resubmit at {_PLATFORM_URL}/account/kyc"
    )


def _t_password_reset_plain(ctx: dict) -> str:
    reset_url = ctx.get("reset_url", _PLATFORM_URL)
    return (
        f"Lingi7: You requested a password reset. "
        f"Click here to reset: {reset_url} "
        f"This link expires in 1 hour. If you did not request this, ignore this message."
    )


def _t_login_otp_plain(ctx: dict) -> str:
    otp = ctx.get("otp", "")
    return (
        f"Lingi7: Your verification code is {otp}. "
        f"It expires in 10 minutes. Do not share this code with anyone."
    )


def _t_order_auto_confirmed_plain(ctx: dict) -> str:
    order_id = ctx.get("order_id", "")
    return (
        f"Lingi7: Order #{order_id} has been auto-confirmed after the delivery window. "
        f"Funds have been released to the seller. Raise a dispute within 24 hours if you "
        f"did not receive your order: {_PLATFORM_URL}/disputes/new"
    )


# ---------------------------------------------------------------------------
# Template Registry
# ---------------------------------------------------------------------------


class TemplateRegistry:
    """
    Static registry mapping event types to NotificationTemplate instances.

    Both SMS and email registries are separate — not every event type
    needs both channels.
    """

    _sms: dict[str, NotificationTemplate] = {}
    _email: dict[str, NotificationTemplate] = {}

    @classmethod
    def register_sms(cls, event_type: str, plain_fn: Callable) -> None:
        """Register an SMS template for the given event type."""
        cls._sms[event_type] = NotificationTemplate(
            event_type=event_type,
            plain_fn=plain_fn,
        )

    @classmethod
    def register_email(
        cls,
        event_type: str,
        subject_fn: Callable,
        plain_fn: Callable,
        html_fn: Optional[Callable] = None,
    ) -> None:
        """Register an email template for the given event type."""
        cls._email[event_type] = NotificationTemplate(
            event_type=event_type,
            subject_fn=subject_fn,
            plain_fn=plain_fn,
            html_fn=html_fn,
        )

    @classmethod
    def get_sms(cls, event_type: str) -> Optional[NotificationTemplate]:
        """Look up a registered SMS template."""
        return cls._sms.get(event_type)

    @classmethod
    def get_email(cls, event_type: str) -> Optional[NotificationTemplate]:
        """Look up a registered email template."""
        return cls._email.get(event_type)


# ---------------------------------------------------------------------------
# Register all templates
# ---------------------------------------------------------------------------

from .models import NotificationEventType as E  # noqa: E402 — after class definition

# SMS templates
_sms_map = [
    (E.WELCOME, _t_welcome_plain),
    (E.PAYMENT_SUCCESS, _t_payment_success_plain),
    (E.PAYMENT_FAILED, _t_payment_failed_plain),
    (E.ORDER_PLACED, _t_order_placed_plain),
    (E.ORDER_SHIPPED, _t_order_shipped_plain),
    (E.ORDER_DELIVERED, _t_order_delivered_plain),
    (E.ORDER_AUTO_CONFIRMED, _t_order_auto_confirmed_plain),
    (E.ESCROW_RELEASED, _t_escrow_released_plain),
    (E.ESCROW_FROZEN, _t_escrow_frozen_plain),
    (E.DISPUTE_OPENED, _t_dispute_opened_plain),
    (E.DISPUTE_RESOLVED, _t_dispute_resolved_plain),
    (E.STORE_APPROVED, _t_store_approved_plain),
    (E.STORE_REJECTED, _t_store_rejected_plain),
    (E.STORE_SUSPENDED, _t_store_suspended_plain),
    (E.LISTING_APPROVED, _t_listing_approved_plain),
    (E.LISTING_REJECTED, _t_listing_rejected_plain),
    (E.KYC_APPROVED, _t_kyc_approved_plain),
    (E.KYC_REJECTED, _t_kyc_rejected_plain),
    (E.PASSWORD_RESET, _t_password_reset_plain),
    (E.LOGIN_OTP, _t_login_otp_plain),
]

for _event, _fn in _sms_map:
    TemplateRegistry.register_sms(_event, _fn)

# Email templates (subject, plain, html)
_email_map = [
    (E.WELCOME, lambda ctx: "Welcome to Lingi7!", _t_welcome_plain, _t_welcome_html),
    (
        E.PAYMENT_SUCCESS,
        lambda ctx: f"Payment Confirmed — Order #{ctx.get('order_id', '')}",
        _t_payment_success_plain,
        _t_payment_success_html,
    ),
    (
        E.PAYMENT_RECEIPT,
        lambda ctx: f"Your Lingi7 Receipt — Order #{ctx.get('order_id', '')}",
        _t_payment_success_plain,
        _t_payment_success_html,
    ),
    (
        E.PAYMENT_FAILED,
        lambda ctx: f"Payment Failed — Order #{ctx.get('order_id', '')}",
        _t_payment_failed_plain,
        None,
    ),
    (
        E.ORDER_SHIPPED,
        lambda ctx: f"Your Order #{ctx.get('order_id', '')} Has Shipped",
        _t_order_shipped_plain,
        _t_order_shipped_html,
    ),
    (
        E.ORDER_DELIVERED,
        lambda ctx: f"Confirm Delivery — Order #{ctx.get('order_id', '')}",
        _t_order_delivered_plain,
        None,
    ),
    (
        E.ESCROW_RELEASED,
        lambda ctx: f"Payout Sent — Order #{ctx.get('order_id', '')}",
        _t_escrow_released_plain,
        _t_escrow_released_html,
    ),
    (
        E.DISPUTE_OPENED,
        lambda ctx: f"Dispute Opened — Order #{ctx.get('order_id', '')}",
        _t_dispute_opened_plain,
        None,
    ),
    (
        E.DISPUTE_RESOLVED,
        lambda ctx: f"Dispute Resolved — Order #{ctx.get('order_id', '')}",
        _t_dispute_resolved_plain,
        None,
    ),
    (
        E.STORE_APPROVED,
        lambda ctx: f"Your Store '{ctx.get('store_name', '')}' is Now Live!",
        _t_store_approved_plain,
        None,
    ),
    (
        E.STORE_REJECTED,
        lambda ctx: "Your Lingi7 Store Application",
        _t_store_rejected_plain,
        None,
    ),
    (
        E.KYC_APPROVED,
        lambda ctx: "Identity Verified — Welcome to Lingi7",
        _t_kyc_approved_plain,
        None,
    ),
    (
        E.KYC_REJECTED,
        lambda ctx: "KYC Verification — Action Required",
        _t_kyc_rejected_plain,
        None,
    ),
    (
        E.PASSWORD_RESET,
        lambda ctx: "Reset Your Lingi7 Password",
        _t_password_reset_plain,
        None,
    ),
]

for _event, _sub_fn, _plain_fn, _html_fn in _email_map:
    TemplateRegistry.register_email(_event, _sub_fn, _plain_fn, _html_fn)
