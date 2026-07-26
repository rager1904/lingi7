"""
apps/fraud/feature_extractor.py

Extracts and engineers features for a given order_id.
Used by both the ML scorer and the Layer 1 rule engine context builder.

Document Ref: LG7-BE-008
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.fraud.models import IPBlacklist
from apps.fraud.rules import RuleContext

logger = logging.getLogger(__name__)


@dataclass
class MLFeatures:
    """
    Feature vector for XGBoost fraud scorer.

    All features are scalar (int/float) — no categorical encoding needed
    at inference time as the model handles this internally.
    """

    order_value_zmw: float
    account_age_days: int
    payment_method_age_hours: float
    recent_failed_payments: int
    recent_orders_count: int
    address_match_score: float  # 0.0 = different, 1.0 = exact match
    hour_of_day: int  # 0–23 — time-of-day fraud signal
    ip_is_blacklisted: int  # 0 or 1

    def to_list(self) -> list[float]:
        """Ordered feature vector for model inference."""
        return [
            self.order_value_zmw,
            float(self.account_age_days),
            self.payment_method_age_hours,
            float(self.recent_failed_payments),
            float(self.recent_orders_count),
            self.address_match_score,
            float(self.hour_of_day),
            float(self.ip_is_blacklisted),
        ]

    @classmethod
    def feature_names(cls) -> list[str]:
        """Feature names in the same order as to_list(). Used for SHAP logging."""
        return [
            "order_value_zmw",
            "account_age_days",
            "payment_method_age_hours",
            "recent_failed_payments",
            "recent_orders_count",
            "address_match_score",
            "hour_of_day",
            "ip_is_blacklisted",
        ]


class FeatureExtractor:
    """
    Builds RuleContext and MLFeatures for a given order.

    Single DB entry point for all fraud feature extraction. Centralising
    here ensures consistent features between Layer 1 and Layer 2.

    Velocity windows are read from the FraudRule model when available,
    falling back to the defaults defined here. This allows threshold
    tuning without a code deploy.
    """

    DEFAULT_PAYMENT_VELOCITY_MINUTES = 10
    DEFAULT_ORDER_VELOCITY_MINUTES = 60

    @classmethod
    def _get_configurable_windows(cls) -> tuple[int, int]:
        """Read velocity windows from FraudRule config, fallback to defaults."""
        try:
            from apps.fraud.models import FraudRule
            payment_window = FraudRule.objects.filter(
                code=FraudRule.RuleCode.PAYMENT_VELOCITY,
                is_active=True,
            ).values_list("payment_attempts_window_minutes", flat=True).first()
            order_window = FraudRule.objects.filter(
                code=FraudRule.RuleCode.ORDER_VELOCITY,
                is_active=True,
            ).values_list("order_velocity_window_minutes", flat=True).first()
            return (
                payment_window or cls.DEFAULT_PAYMENT_VELOCITY_MINUTES,
                order_window or cls.DEFAULT_ORDER_VELOCITY_MINUTES,
            )
        except Exception:  # noqa: BLE001
            return cls.DEFAULT_PAYMENT_VELOCITY_MINUTES, cls.DEFAULT_ORDER_VELOCITY_MINUTES

    @classmethod
    def build_rule_context(cls, order_id: int) -> RuleContext:
        """
        Fetch all data needed for Layer 1 rule evaluation.

        Args:
            order_id: PK of the order to evaluate.

        Returns:
            RuleContext with pre-fetched data. No DB calls made in rules.

        Raises:
            Order.DoesNotExist: If order_id is invalid.
        """
        # Late import to avoid circular dependency
        from apps.orders.models import Order
        from apps.payments.models import PaymentAttempt

        order = (
            Order.objects.select_related("buyer", "buyer__profile")
            .get(pk=order_id)
        )
        buyer = order.buyer

        now = timezone.now()
        account_age = (now - buyer.date_joined).days

        # Use configurable velocity windows from FraudRule model
        payment_velocity_minutes, order_velocity_minutes = cls._get_configurable_windows()

        # Recent failed payment attempts
        payment_window = now - timedelta(minutes=payment_velocity_minutes)
        recent_failed = PaymentAttempt.objects.filter(
            initiated_by=buyer,
            status="FAILED",
            created_at__gte=payment_window,
        ).count()

        # Recent order velocity
        order_window = now - timedelta(minutes=order_velocity_minutes)
        recent_orders = Order.objects.filter(
            buyer=buyer,
            created_at__gte=order_window,
        ).count()

        # Pre-load active blacklist for O(1) rule lookup
        blacklisted_ips = frozenset(
            IPBlacklist.objects.filter(is_active=True).values_list("ip_address", flat=True)
        )

        # Payment method age — hours since first MoMo/Airtel use by this buyer
        # Approximated from PaymentAttempt history until dedicated PaymentMethod model added
        first_payment = PaymentAttempt.objects.filter(initiated_by=buyer).order_by("created_at").first()
        if first_payment:
            payment_method_age_hours = (now - first_payment.created_at).total_seconds() / 3600
        else:
            payment_method_age_hours = 0.0

        registration_address = getattr(buyer, "address", "") or ""
        shipping_address = getattr(order, "shipping_address", "") or ""

        return RuleContext(
            order_id=order_id,
            order_value_zmw=order.total_amount,
            buyer_account_age_days=account_age,
            buyer_ip_address=getattr(order, "buyer_ip_address", "") or "",
            buyer_registration_address=registration_address,
            shipping_address=shipping_address,
            payment_method_added_at_hours_ago=payment_method_age_hours,
            recent_payment_attempts=recent_failed,
            recent_orders_count=recent_orders,
            blacklisted_ips=blacklisted_ips,
        )

    @classmethod
    def build_ml_features(cls, order_id: int) -> MLFeatures:
        """
        Build the ML feature vector for XGBoost inference.

        Args:
            order_id: PK of the order to score.

        Returns:
            MLFeatures dataclass ready for model.predict().
        """
        ctx = cls.build_rule_context(order_id)
        now = timezone.now()

        address_match = (
            1.0
            if ctx.buyer_registration_address.strip().lower()
            == ctx.shipping_address.strip().lower()
            else 0.0
        )

        return MLFeatures(
            order_value_zmw=float(ctx.order_value_zmw),
            account_age_days=ctx.buyer_account_age_days,
            payment_method_age_hours=ctx.payment_method_added_at_hours_ago,
            recent_failed_payments=ctx.recent_payment_attempts,
            recent_orders_count=ctx.recent_orders_count,
            address_match_score=address_match,
            hour_of_day=now.hour,
            ip_is_blacklisted=1 if ctx.buyer_ip_address in ctx.blacklisted_ips else 0,
        )
