"""
apps/fraud/models.py

Fraud detection models: FraudEvent, FraudRule, IPBlacklist.
Every fraud flag is persisted for audit, ML retraining, and compliance.

Document Ref: LG7-BE-008
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class FraudRule(models.Model):
    """
    Configurable Layer 1 rule definitions.

    Rules are loaded from the database so thresholds can be tuned
    without a code deploy. Each rule maps to a method in FraudRuleEngine.
    """

    class RuleCode(models.TextChoices):
        NEW_ACCOUNT_HIGH_VALUE = "NEW_ACCOUNT_HIGH_VALUE", "New Account + High Value Order"
        IP_BLACKLIST = "IP_BLACKLIST", "IP Address Blacklisted"
        PAYMENT_VELOCITY = "PAYMENT_VELOCITY", "Payment Attempt Velocity"
        ADDRESS_MISMATCH = "ADDRESS_MISMATCH", "Shipping Address Mismatch"
        ORDER_VELOCITY = "ORDER_VELOCITY", "Order Placement Velocity"
        PAYMENT_METHOD_NEW = "PAYMENT_METHOD_NEW", "New Payment Method + High Value"

    code = models.CharField(
        max_length=40,
        choices=RuleCode.choices,
        unique=True,
    )
    description = models.TextField()
    is_active = models.BooleanField(default=True)

    # Configurable thresholds — tunable without code deploy
    account_age_days_threshold = models.PositiveIntegerField(default=7)
    order_value_threshold_zmw = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("5000.00")
    )
    payment_attempts_window_minutes = models.PositiveIntegerField(default=10)
    payment_attempts_count_threshold = models.PositiveIntegerField(default=3)
    order_velocity_window_minutes = models.PositiveIntegerField(default=60)
    order_velocity_count_threshold = models.PositiveIntegerField(default=3)
    payment_method_age_hours_threshold = models.PositiveIntegerField(default=24)
    address_mismatch_account_age_days = models.PositiveIntegerField(default=30)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "fraud_rule"
        verbose_name = "Fraud Rule"
        verbose_name_plural = "Fraud Rules"

    def __str__(self) -> str:
        status = "active" if self.is_active else "disabled"
        return f"{self.get_code_display()} [{status}]"


class IPBlacklist(models.Model):
    """
    IP addresses flagged for fraudulent activity.

    Added manually via admin or automatically by fraud spike detection.
    Synced to Cloudflare WAF via Celery task.
    """

    ip_address = models.GenericIPAddressField(unique=True, db_index=True)
    reason = models.TextField()
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="blacklisted_ips",
    )
    is_active = models.BooleanField(default=True)
    cloudflare_synced = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "fraud_ip_blacklist"
        verbose_name = "IP Blacklist Entry"
        verbose_name_plural = "IP Blacklist"

    def __str__(self) -> str:
        return f"{self.ip_address} ({'active' if self.is_active else 'inactive'})"


class FraudEvent(models.Model):
    """
    Immutable record of every fraud flag raised against an order.

    One FraudEvent per rule triggered, per evaluation. Multiple events
    may exist for a single order if the fraud pipeline is re-run.
    This table is the primary training data source for the ML model.
    """

    class Verdict(models.TextChoices):
        FLAGGED = "FLAGGED", "Flagged — Review Required"
        CLEARED = "CLEARED", "Cleared — No Fraud Signals"
        FROZEN = "FROZEN", "Frozen — Manual Review Mandatory"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="fraud_events",
        db_index=True,
    )
    rule_triggered = models.CharField(
        max_length=40,
        choices=FraudRule.RuleCode.choices,
        blank=True,
        help_text="Empty when event represents ML verdict rather than a specific rule.",
    )
    verdict = models.CharField(max_length=10, choices=Verdict.choices)

    # ML scoring fields
    ml_risk_score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="XGBoost risk score 0.0–1.0. Null if ML scoring not yet active.",
    )
    ml_freeze_threshold = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Threshold at time of scoring — captures config at decision time.",
    )

    # Snapshot of features used (for auditability and retraining)
    feature_snapshot = models.JSONField(
        default=dict,
        help_text="All ML features at time of scoring. Immutable after creation.",
    )

    # SHAP explainability (populated when ML scorer is active)
    shap_values = models.JSONField(
        default=dict,
        help_text="SHAP values per feature for compliance explainability.",
    )

    notes = models.TextField(blank=True)
    evaluated_at = models.DateTimeField(default=timezone.now)

    # Outcome tracking — updated when order is resolved
    outcome_confirmed_fraud = models.BooleanField(
        null=True,
        blank=True,
        help_text="Set post-resolution: True=confirmed fraud, False=false positive, None=pending.",
    )
    outcome_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "fraud_event"
        verbose_name = "Fraud Event"
        verbose_name_plural = "Fraud Events"
        indexes = [
            models.Index(fields=["order", "evaluated_at"]),
            models.Index(fields=["verdict", "evaluated_at"]),
            models.Index(fields=["rule_triggered"]),
        ]
        # Prevent accidental updates — fraud events are append-only
        # Enforce this at service layer: never call .save() on an existing FraudEvent

    def __str__(self) -> str:
        return f"FraudEvent[{self.order_id}] verdict={self.verdict} rule={self.rule_triggered or 'ML'}"
