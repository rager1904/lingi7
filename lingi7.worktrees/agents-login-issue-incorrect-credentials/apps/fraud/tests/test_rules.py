"""
apps/fraud/tests/test_rules.py

Unit tests for all 6 Layer 1 fraud rules.
Each rule has: a trigger case, a no-trigger case, and an edge case.

Document Ref: LG7-BE-008
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.fraud.rules import FraudRuleEngine, RuleContext


def make_context(**overrides) -> RuleContext:
    """Build a clean (non-fraudulent) RuleContext with safe defaults."""
    defaults = {
        "order_id": 1,
        "order_value_zmw": Decimal("500.00"),
        "buyer_account_age_days": 60,
        "buyer_ip_address": "196.1.2.3",
        "buyer_registration_address": "Plot 15, Cairo Road, Lusaka",
        "shipping_address": "Plot 15, Cairo Road, Lusaka",
        "payment_method_added_at_hours_ago": 72.0,
        "recent_payment_attempts": 0,
        "recent_orders_count": 1,
        "blacklisted_ips": frozenset(),
    }
    defaults.update(overrides)
    return RuleContext(**defaults)


@pytest.fixture
def engine() -> FraudRuleEngine:
    return FraudRuleEngine()


# ──────────────────────────────────────────────────────────────────────
# Rule 1: New account + high value
# ──────────────────────────────────────────────────────────────────────

class TestRuleNewAccountHighValue:
    def test_triggers_when_new_account_and_high_value(self, engine):
        ctx = make_context(buyer_account_age_days=3, order_value_zmw=Decimal("6000.00"))
        result = engine.rule_new_account_high_value(ctx)
        assert result.triggered is True
        assert "6000" in result.reason or "6" in result.reason

    def test_no_trigger_old_account_high_value(self, engine):
        ctx = make_context(buyer_account_age_days=30, order_value_zmw=Decimal("6000.00"))
        result = engine.rule_new_account_high_value(ctx)
        assert result.triggered is False

    def test_no_trigger_new_account_low_value(self, engine):
        ctx = make_context(buyer_account_age_days=3, order_value_zmw=Decimal("500.00"))
        result = engine.rule_new_account_high_value(ctx)
        assert result.triggered is False

    def test_boundary_exactly_at_threshold(self, engine):
        # Exactly at threshold — should NOT trigger (must be strictly greater)
        ctx = make_context(buyer_account_age_days=7, order_value_zmw=Decimal("5000.00"))
        result = engine.rule_new_account_high_value(ctx)
        # account_age == threshold means NOT new (< 7 is new)
        assert result.triggered is False

    def test_one_day_old_account_just_over_threshold(self, engine):
        ctx = make_context(buyer_account_age_days=1, order_value_zmw=Decimal("5001.00"))
        result = engine.rule_new_account_high_value(ctx)
        assert result.triggered is True


# ──────────────────────────────────────────────────────────────────────
# Rule 2: IP Blacklist
# ──────────────────────────────────────────────────────────────────────

class TestRuleIPBlacklist:
    def test_triggers_on_blacklisted_ip(self, engine):
        bad_ip = "197.5.10.1"
        ctx = make_context(buyer_ip_address=bad_ip, blacklisted_ips=frozenset([bad_ip, "10.0.0.1"]))
        result = engine.rule_ip_blacklist(ctx)
        assert result.triggered is True
        assert bad_ip in result.reason

    def test_no_trigger_clean_ip(self, engine):
        ctx = make_context(
            buyer_ip_address="196.1.2.3",
            blacklisted_ips=frozenset(["197.5.10.1", "10.0.0.1"]),
        )
        result = engine.rule_ip_blacklist(ctx)
        assert result.triggered is False

    def test_no_trigger_empty_blacklist(self, engine):
        ctx = make_context(buyer_ip_address="196.1.2.3", blacklisted_ips=frozenset())
        result = engine.rule_ip_blacklist(ctx)
        assert result.triggered is False

    def test_triggers_single_entry_blacklist(self, engine):
        ip = "41.175.22.99"
        ctx = make_context(buyer_ip_address=ip, blacklisted_ips=frozenset([ip]))
        result = engine.rule_ip_blacklist(ctx)
        assert result.triggered is True


# ──────────────────────────────────────────────────────────────────────
# Rule 3: Payment attempt velocity
# ──────────────────────────────────────────────────────────────────────

class TestRulePaymentVelocity:
    def test_triggers_at_threshold(self, engine):
        ctx = make_context(recent_payment_attempts=3)
        result = engine.rule_payment_velocity(ctx)
        assert result.triggered is True

    def test_triggers_above_threshold(self, engine):
        ctx = make_context(recent_payment_attempts=10)
        result = engine.rule_payment_velocity(ctx)
        assert result.triggered is True

    def test_no_trigger_below_threshold(self, engine):
        ctx = make_context(recent_payment_attempts=2)
        result = engine.rule_payment_velocity(ctx)
        assert result.triggered is False

    def test_no_trigger_zero_attempts(self, engine):
        ctx = make_context(recent_payment_attempts=0)
        result = engine.rule_payment_velocity(ctx)
        assert result.triggered is False


# ──────────────────────────────────────────────────────────────────────
# Rule 4: Address mismatch on young accounts
# ──────────────────────────────────────────────────────────────────────

class TestRuleAddressMismatch:
    def test_triggers_young_account_different_address(self, engine):
        ctx = make_context(
            buyer_account_age_days=10,
            buyer_registration_address="Plot 15, Cairo Road, Lusaka",
            shipping_address="12 Independence Ave, Ndola",
        )
        result = engine.rule_address_mismatch(ctx)
        assert result.triggered is True

    def test_no_trigger_old_account_different_address(self, engine):
        # Established accounts shipping to different address is normal
        ctx = make_context(
            buyer_account_age_days=60,
            buyer_registration_address="Plot 15, Cairo Road, Lusaka",
            shipping_address="12 Independence Ave, Ndola",
        )
        result = engine.rule_address_mismatch(ctx)
        assert result.triggered is False

    def test_no_trigger_young_account_same_address(self, engine):
        ctx = make_context(
            buyer_account_age_days=5,
            buyer_registration_address="Plot 15, Cairo Road, Lusaka",
            shipping_address="Plot 15, Cairo Road, Lusaka",
        )
        result = engine.rule_address_mismatch(ctx)
        assert result.triggered is False

    def test_case_insensitive_address_comparison(self, engine):
        ctx = make_context(
            buyer_account_age_days=5,
            buyer_registration_address="Plot 15, CAIRO ROAD, LUSAKA",
            shipping_address="plot 15, cairo road, lusaka",
        )
        result = engine.rule_address_mismatch(ctx)
        # Same address, different case — should NOT trigger
        assert result.triggered is False


# ──────────────────────────────────────────────────────────────────────
# Rule 5: Order velocity
# ──────────────────────────────────────────────────────────────────────

class TestRuleOrderVelocity:
    def test_triggers_at_threshold(self, engine):
        ctx = make_context(recent_orders_count=3)
        result = engine.rule_order_velocity(ctx)
        assert result.triggered is True

    def test_triggers_above_threshold(self, engine):
        ctx = make_context(recent_orders_count=7)
        result = engine.rule_order_velocity(ctx)
        assert result.triggered is True

    def test_no_trigger_below_threshold(self, engine):
        ctx = make_context(recent_orders_count=2)
        result = engine.rule_order_velocity(ctx)
        assert result.triggered is False

    def test_no_trigger_single_order(self, engine):
        ctx = make_context(recent_orders_count=1)
        result = engine.rule_order_velocity(ctx)
        assert result.triggered is False


# ──────────────────────────────────────────────────────────────────────
# Rule 6: New payment method + high value
# ──────────────────────────────────────────────────────────────────────

class TestRulePaymentMethodNew:
    def test_triggers_new_method_high_value(self, engine):
        ctx = make_context(
            payment_method_added_at_hours_ago=2.0,
            order_value_zmw=Decimal("8000.00"),
        )
        result = engine.rule_payment_method_new(ctx)
        assert result.triggered is True

    def test_no_trigger_old_method_high_value(self, engine):
        ctx = make_context(
            payment_method_added_at_hours_ago=72.0,
            order_value_zmw=Decimal("8000.00"),
        )
        result = engine.rule_payment_method_new(ctx)
        assert result.triggered is False

    def test_no_trigger_new_method_low_value(self, engine):
        ctx = make_context(
            payment_method_added_at_hours_ago=1.0,
            order_value_zmw=Decimal("500.00"),
        )
        result = engine.rule_payment_method_new(ctx)
        assert result.triggered is False

    def test_boundary_exactly_24_hours(self, engine):
        # Exactly 24h — NOT within threshold (< 24h triggers)
        ctx = make_context(
            payment_method_added_at_hours_ago=24.0,
            order_value_zmw=Decimal("6000.00"),
        )
        result = engine.rule_payment_method_new(ctx)
        assert result.triggered is False


# ──────────────────────────────────────────────────────────────────────
# Combined evaluation
# ──────────────────────────────────────────────────────────────────────

class TestFraudRuleEngineEvaluate:
    def test_clean_order_triggers_no_rules(self, engine):
        ctx = make_context()
        result = engine.evaluate(ctx)
        assert result.should_flag is False
        assert len(result.triggered_codes) == 0

    def test_multiple_rules_trigger_simultaneously(self, engine):
        bad_ip = "197.5.10.1"
        ctx = make_context(
            buyer_account_age_days=2,
            order_value_zmw=Decimal("9000.00"),
            buyer_ip_address=bad_ip,
            blacklisted_ips=frozenset([bad_ip]),
            recent_payment_attempts=5,
        )
        result = engine.evaluate(ctx)
        assert result.should_flag is True
        assert "NEW_ACCOUNT_HIGH_VALUE" in result.triggered_codes
        assert "IP_BLACKLIST" in result.triggered_codes
        assert "PAYMENT_VELOCITY" in result.triggered_codes

    def test_custom_thresholds_override_defaults(self):
        config = {
            "NEW_ACCOUNT_HIGH_VALUE": {
                "account_age_days_threshold": 30,
                "order_value_threshold_zmw": "1000.00",
            }
        }
        engine = FraudRuleEngine(rules_config=config)
        # 20-day old account, ZMW 1500 order — should trigger with custom threshold
        ctx = make_context(buyer_account_age_days=20, order_value_zmw=Decimal("1500.00"))
        result = engine.rule_new_account_high_value(ctx)
        assert result.triggered is True
