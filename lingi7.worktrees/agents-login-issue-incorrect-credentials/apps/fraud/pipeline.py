"""
apps/fraud/pipeline.py

FraudPipeline — orchestrates Layer 1 (rules) then Layer 2 (ML scorer).

This is the sole entry point called by EscrowService before every
RELEASED transition. It persists FraudEvent records and raises
FraudGateError if the order should be frozen.

Document Ref: LG7-BE-008
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.fraud.exceptions import FraudGateError
from apps.fraud.feature_extractor import FeatureExtractor, MLFeatures
from apps.fraud.models import FraudEvent, FraudRule
from apps.fraud.rules import FraudRuleEngine, LayerOneResult, RuleContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineVerdict:
    """
    Final verdict from the full fraud pipeline.

    Returned to EscrowService. If should_freeze is True, EscrowService
    must move the escrow to FROZEN state and raise FraudGateError.
    """

    order_id: int
    should_freeze: bool
    triggered_rule_codes: list[str]
    ml_risk_score: Decimal | None
    ml_shap_values: dict[str, float]
    verdict_label: str  # "CLEARED" | "FLAGGED" | "FROZEN"


class FraudPipeline:
    """
    Two-layer fraud detection pipeline.

    Layer 1: FraudRuleEngine — deterministic rules, microsecond latency.
    Layer 2: MLScorer — XGBoost risk scoring, < 50ms latency.

    Layer 2 is only invoked when the ML model is configured. In early
    Phase 1 deployment, Layer 1 alone is sufficient.

    All fraud events are persisted as FraudEvent records. The pipeline
    itself does NOT freeze the escrow — that is EscrowService's responsibility.
    """

    @classmethod
    def run(cls, order_id: int) -> PipelineVerdict:
        """
        Execute the full fraud pipeline for a given order.

        This method must be called within EscrowService's atomic block.
        It does not perform its own transaction.atomic() wrapper — the
        caller's transaction context applies.

        Args:
            order_id: PK of the order being evaluated.

        Returns:
            PipelineVerdict with should_freeze flag and scoring details.

        Raises:
            Order.DoesNotExist: If order_id is invalid.
        """
        logger.info("FraudPipeline starting", extra={"order_id": order_id})

        # ── Layer 1: Rule Engine ──────────────────────────────────
        rules_config = cls._load_rules_config()
        rule_engine = FraudRuleEngine(rules_config)

        try:
            ctx: RuleContext = FeatureExtractor.build_rule_context(order_id)
        except Exception as exc:
            logger.exception("Feature extraction failed", extra={"order_id": order_id})
            # Fail-safe: if we can't extract features, freeze the order
            cls._persist_event(
                order_id=order_id,
                rule_triggered="",
                verdict=FraudEvent.Verdict.FROZEN,
                notes=f"Feature extraction failed: {exc}. Order frozen as precaution.",
            )
            return PipelineVerdict(
                order_id=order_id,
                should_freeze=True,
                triggered_rule_codes=[],
                ml_risk_score=None,
                ml_shap_values={},
                verdict_label="FROZEN",
            )

        layer1_result: LayerOneResult = rule_engine.evaluate(ctx)

        # Persist a FraudEvent for each triggered rule
        for rule_result in layer1_result.triggered_rules:
            cls._persist_event(
                order_id=order_id,
                rule_triggered=rule_result.rule_code,
                verdict=FraudEvent.Verdict.FLAGGED,
                notes=rule_result.reason,
            )

        # ── Layer 2: ML Scorer ────────────────────────────────────
        ml_risk_score: Decimal | None = None
        ml_shap_values: dict[str, float] = {}
        ml_should_freeze = False

        try:
            from apps.fraud.ml_scorer import MLScorer

            ml_features: MLFeatures = FeatureExtractor.build_ml_features(order_id)
            ml_result = MLScorer.score(
                features=ml_features.to_list(),
                feature_names=MLFeatures.feature_names(),
            )
            ml_risk_score = ml_result.risk_score
            ml_shap_values = ml_result.shap_values
            ml_should_freeze = ml_result.should_freeze

            ml_verdict = (
                FraudEvent.Verdict.FROZEN if ml_should_freeze else FraudEvent.Verdict.CLEARED
            )

            cls._persist_event(
                order_id=order_id,
                rule_triggered="",
                verdict=ml_verdict,
                ml_risk_score=ml_risk_score,
                ml_freeze_threshold=ml_result.freeze_threshold,
                feature_snapshot={
                    name: val
                    for name, val in zip(MLFeatures.feature_names(), ml_features.to_list())
                },
                shap_values=ml_shap_values,
                notes=f"ML score: {ml_risk_score} (threshold: {ml_result.freeze_threshold})",
            )

            logger.info(
                "ML fraud score computed",
                extra={
                    "order_id": order_id,
                    "risk_score": str(ml_risk_score),
                    "should_freeze": ml_should_freeze,
                    "model_version": ml_result.model_version,
                },
            )
        except RuntimeError as exc:
            # ML model not configured or unavailable — Layer 1 only mode
            logger.warning(
                "ML scorer unavailable — operating in Layer 1 only mode",
                extra={"order_id": order_id, "reason": str(exc)},
            )
        except Exception:
            logger.exception(
                "ML scoring failed unexpectedly",
                extra={"order_id": order_id},
            )

        # ── Final Verdict ─────────────────────────────────────────
        should_freeze = layer1_result.should_flag or ml_should_freeze

        if should_freeze:
            verdict_label = "FROZEN"
        elif layer1_result.should_flag:
            verdict_label = "FLAGGED"
        else:
            verdict_label = "CLEARED"

        logger.info(
            "FraudPipeline complete",
            extra={
                "order_id": order_id,
                "verdict": verdict_label,
                "triggered_rules": layer1_result.triggered_codes,
                "ml_risk_score": str(ml_risk_score) if ml_risk_score is not None else None,
            },
        )

        return PipelineVerdict(
            order_id=order_id,
            should_freeze=should_freeze,
            triggered_rule_codes=layer1_result.triggered_codes,
            ml_risk_score=ml_risk_score,
            ml_shap_values=ml_shap_values,
            verdict_label=verdict_label,
        )

    @classmethod
    def _persist_event(
        cls,
        order_id: int,
        rule_triggered: str,
        verdict: str,
        ml_risk_score: Decimal | None = None,
        ml_freeze_threshold: Decimal | None = None,
        feature_snapshot: dict | None = None,
        shap_values: dict | None = None,
        notes: str = "",
    ) -> FraudEvent:
        """Persist a FraudEvent. Called within the caller's transaction."""
        from apps.orders.models import Order

        return FraudEvent.objects.create(
            order_id=order_id,
            rule_triggered=rule_triggered,
            verdict=verdict,
            ml_risk_score=ml_risk_score,
            ml_freeze_threshold=ml_freeze_threshold,
            feature_snapshot=feature_snapshot or {},
            shap_values=shap_values or {},
            notes=notes,
            evaluated_at=timezone.now(),
        )

    @staticmethod
    def _load_rules_config() -> dict:
        """
        Load active FraudRule thresholds from DB into a dict.

        Returns a nested dict keyed by rule code for O(1) access in rules.
        """
        config: dict = {}
        try:
            for rule in FraudRule.objects.filter(is_active=True):
                config[rule.code] = {
                    "account_age_days_threshold": rule.account_age_days_threshold,
                    "order_value_threshold_zmw": str(rule.order_value_threshold_zmw),
                    "payment_attempts_count_threshold": rule.payment_attempts_count_threshold,
                    "order_velocity_count_threshold": rule.order_velocity_count_threshold,
                    "payment_method_age_hours_threshold": rule.payment_method_age_hours_threshold,
                    "address_mismatch_account_age_days": rule.address_mismatch_account_age_days,
                }
        except Exception:
            logger.warning("Could not load FraudRule config from DB — using defaults")
        return config
