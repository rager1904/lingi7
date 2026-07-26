"""
apps/fraud/rules.py

Layer 1 deterministic fraud rule engine.

Each rule is implemented as an isolated, independently-testable method.
Rules are designed to run in microseconds — no external I/O, no DB writes.
All DB reads are passed in as pre-fetched context to keep rules pure functions.

Document Ref: LG7-BE-008
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuleContext:
    """
    Snapshot of all data required for Layer 1 rule evaluation.

    Pre-fetched by FraudPipeline before calling the rule engine.
    Rules must not perform additional DB queries — all needed data lives here.
    """

    order_id: int
    order_value_zmw: Decimal
    buyer_account_age_days: int
    buyer_ip_address: str
    buyer_registration_address: str
    shipping_address: str
    payment_method_added_at_hours_ago: float  # hours since payment method was added
    recent_payment_attempts: int  # failed attempts in last N minutes
    recent_orders_count: int  # orders placed in last N minutes
    blacklisted_ips: frozenset[str]  # pre-loaded blacklist for O(1) lookup
    thresholds: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleResult:
    """Result from a single rule evaluation."""

    rule_code: str
    triggered: bool
    reason: str = ""


@dataclass
class LayerOneResult:
    """Aggregate result from all Layer 1 rules."""

    triggered_rules: list[RuleResult]
    should_flag: bool

    @property
    def triggered_codes(self) -> list[str]:
        return [r.rule_code for r in self.triggered_rules if r.triggered]


class FraudRuleEngine:
    """
    Deterministic Layer 1 fraud rule engine.

    All rules are pure functions — given the same RuleContext they always
    return the same result. This makes them trivially testable and auditable.

    Usage:
        context = RuleContext(...)
        engine = FraudRuleEngine(rules_config)
        result = engine.evaluate(context)
    """

    # Default thresholds — overridden by DB-persisted FraudRule instances
    DEFAULT_NEW_ACCOUNT_AGE_DAYS = 7
    DEFAULT_HIGH_VALUE_THRESHOLD_ZMW = Decimal("5000.00")
    DEFAULT_PAYMENT_ATTEMPTS_THRESHOLD = 3
    DEFAULT_ORDER_VELOCITY_THRESHOLD = 3
    DEFAULT_PAYMENT_METHOD_AGE_HOURS = 24
    DEFAULT_ADDRESS_MISMATCH_ACCOUNT_AGE = 30

    def __init__(self, rules_config: dict[str, Any] | None = None) -> None:
        """
        Args:
            rules_config: Dict of threshold overrides keyed by rule code.
                          Loaded from DB-persisted FraudRule instances.
                          Falls back to class-level defaults if None.
        """
        self._config = rules_config or {}

    def _get(self, rule_code: str, key: str, default: Any) -> Any:
        """Retrieve a threshold for a given rule, falling back to default."""
        return self._config.get(rule_code, {}).get(key, default)

    # ──────────────────────────────────────────────────────────────
    # Rule 1: New account + high-value order
    # ──────────────────────────────────────────────────────────────

    def rule_new_account_high_value(self, ctx: RuleContext) -> RuleResult:
        """
        Flag orders where a new account places a high-value order.

        New accounts lack transaction history for fraud baseline — high-value
        orders from them represent disproportionate risk.
        """
        code = "NEW_ACCOUNT_HIGH_VALUE"
        age_threshold = self._get(code, "account_age_days_threshold", self.DEFAULT_NEW_ACCOUNT_AGE_DAYS)
        value_threshold = Decimal(
            str(self._get(code, "order_value_threshold_zmw", self.DEFAULT_HIGH_VALUE_THRESHOLD_ZMW))
        )

        triggered = (
            ctx.buyer_account_age_days < age_threshold
            and ctx.order_value_zmw > value_threshold
        )

        return RuleResult(
            rule_code=code,
            triggered=triggered,
            reason=(
                f"Account is {ctx.buyer_account_age_days} days old "
                f"(threshold: {age_threshold}) and order value ZMW {ctx.order_value_zmw} "
                f"exceeds ZMW {value_threshold}."
            ) if triggered else "",
        )

    # ──────────────────────────────────────────────────────────────
    # Rule 2: IP address in blacklist
    # ──────────────────────────────────────────────────────────────

    def rule_ip_blacklist(self, ctx: RuleContext) -> RuleResult:
        """
        Flag requests originating from blacklisted IP addresses.

        Blacklist is pre-loaded into the RuleContext as a frozenset for O(1)
        lookup — no DB query at rule evaluation time.
        """
        code = "IP_BLACKLIST"
        triggered = ctx.buyer_ip_address in ctx.blacklisted_ips

        return RuleResult(
            rule_code=code,
            triggered=triggered,
            reason=f"IP {ctx.buyer_ip_address} is in the active blacklist." if triggered else "",
        )

    # ──────────────────────────────────────────────────────────────
    # Rule 3: Payment attempt velocity
    # ──────────────────────────────────────────────────────────────

    def rule_payment_velocity(self, ctx: RuleContext) -> RuleResult:
        """
        Flag accounts with multiple failed payment attempts in a short window.

        High failure velocity indicates card testing, credential stuffing,
        or deliberate payment manipulation.
        """
        code = "PAYMENT_VELOCITY"
        threshold = self._get(code, "payment_attempts_count_threshold", self.DEFAULT_PAYMENT_ATTEMPTS_THRESHOLD)

        triggered = ctx.recent_payment_attempts >= threshold

        return RuleResult(
            rule_code=code,
            triggered=triggered,
            reason=(
                f"{ctx.recent_payment_attempts} failed payment attempts detected "
                f"(threshold: {threshold})."
            ) if triggered else "",
        )

    # ──────────────────────────────────────────────────────────────
    # Rule 4: Shipping address mismatch on young accounts
    # ──────────────────────────────────────────────────────────────

    def rule_address_mismatch(self, ctx: RuleContext) -> RuleResult:
        """
        Flag young accounts shipping to an address different from registration.

        Address mismatch on established accounts is normal (gifts, etc.).
        On accounts < 30 days old it is a stronger fraud signal.
        """
        code = "ADDRESS_MISMATCH"
        age_threshold = self._get(code, "address_mismatch_account_age_days", self.DEFAULT_ADDRESS_MISMATCH_ACCOUNT_AGE)

        # Normalise addresses: strip whitespace, lowercase for comparison
        reg_addr_norm = ctx.buyer_registration_address.strip().lower()
        ship_addr_norm = ctx.shipping_address.strip().lower()

        addresses_differ = reg_addr_norm != ship_addr_norm
        account_young = ctx.buyer_account_age_days < age_threshold

        triggered = addresses_differ and account_young

        return RuleResult(
            rule_code=code,
            triggered=triggered,
            reason=(
                f"Shipping address differs from registration address for an account "
                f"{ctx.buyer_account_age_days} days old (threshold: {age_threshold} days)."
            ) if triggered else "",
        )

    # ──────────────────────────────────────────────────────────────
    # Rule 5: Order placement velocity
    # ──────────────────────────────────────────────────────────────

    def rule_order_velocity(self, ctx: RuleContext) -> RuleResult:
        """
        Flag accounts placing multiple orders in a short time window.

        Legitimate buyers rarely place 3+ orders within 60 minutes.
        High velocity suggests automated ordering or account takeover.
        """
        code = "ORDER_VELOCITY"
        threshold = self._get(code, "order_velocity_count_threshold", self.DEFAULT_ORDER_VELOCITY_THRESHOLD)

        triggered = ctx.recent_orders_count >= threshold

        return RuleResult(
            rule_code=code,
            triggered=triggered,
            reason=(
                f"{ctx.recent_orders_count} orders placed in the velocity window "
                f"(threshold: {threshold})."
            ) if triggered else "",
        )

    # ──────────────────────────────────────────────────────────────
    # Rule 6: New payment method + high-value order
    # ──────────────────────────────────────────────────────────────

    def rule_payment_method_new(self, ctx: RuleContext) -> RuleResult:
        """
        Flag high-value orders paid with a payment method added < 24 hours ago.

        Compromised accounts often have new payment methods added immediately
        before fraudulent high-value purchases.
        """
        code = "PAYMENT_METHOD_NEW"
        age_threshold_hours = self._get(
            code, "payment_method_age_hours_threshold", self.DEFAULT_PAYMENT_METHOD_AGE_HOURS
        )
        value_threshold = Decimal(
            str(self._get(code, "order_value_threshold_zmw", self.DEFAULT_HIGH_VALUE_THRESHOLD_ZMW))
        )

        triggered = (
            ctx.payment_method_added_at_hours_ago < age_threshold_hours
            and ctx.order_value_zmw > value_threshold
        )

        return RuleResult(
            rule_code=code,
            triggered=triggered,
            reason=(
                f"Payment method added {ctx.payment_method_added_at_hours_ago:.1f} hours ago "
                f"(threshold: {age_threshold_hours}h) for order value ZMW {ctx.order_value_zmw}."
            ) if triggered else "",
        )

    # ──────────────────────────────────────────────────────────────
    # Orchestrator
    # ──────────────────────────────────────────────────────────────

    def evaluate(self, ctx: RuleContext) -> LayerOneResult:
        """
        Run all active Layer 1 rules against the provided context.

        Args:
            ctx: Pre-fetched RuleContext snapshot for this order.

        Returns:
            LayerOneResult with list of triggered rules and aggregate flag.
        """
        rule_methods = [
            self.rule_new_account_high_value,
            self.rule_ip_blacklist,
            self.rule_payment_velocity,
            self.rule_address_mismatch,
            self.rule_order_velocity,
            self.rule_payment_method_new,
        ]

        triggered: list[RuleResult] = []

        for rule_fn in rule_methods:
            try:
                result = rule_fn(ctx)
                if result.triggered:
                    triggered.append(result)
                    logger.info(
                        "Fraud rule triggered",
                        extra={
                            "order_id": ctx.order_id,
                            "rule_code": result.rule_code,
                            "reason": result.reason,
                        },
                    )
            except Exception:
                logger.exception(
                    "Fraud rule evaluation failed",
                    extra={"order_id": ctx.order_id, "rule": rule_fn.__name__},
                )
                # Never let a rule failure prevent the pipeline from running
                continue

        return LayerOneResult(
            triggered_rules=triggered,
            should_flag=len(triggered) > 0,
        )
