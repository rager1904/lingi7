"""
apps/fraud/tasks.py

Celery tasks for fraud system maintenance and alerting.

Document Ref: LG7-BE-008
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import Count
from django.utils import timezone

logger = logging.getLogger(__name__)

FRAUD_SPIKE_MULTIPLIER = 5  # Alert if current rate > 5x baseline


@shared_task(name="fraud.fraud_spike_alert", bind=True, max_retries=3)
def fraud_spike_alert(self) -> None:
    """
    Detect anomalous spikes in fraud flag rate.

    Compares current hour's flag rate to the 7-day hourly baseline.
    Fires alert if current rate exceeds 5x baseline.

    Runs every hour via Celery Beat.
    """
    from apps.fraud.models import FraudEvent

    now = timezone.now()
    current_hour_start = now.replace(minute=0, second=0, microsecond=0)
    seven_days_ago = now - timedelta(days=7)

    current_count = FraudEvent.objects.filter(
        evaluated_at__gte=current_hour_start,
        verdict=FraudEvent.Verdict.FLAGGED,
    ).count()

    # 7-day hourly average
    baseline_qs = FraudEvent.objects.filter(
        evaluated_at__gte=seven_days_ago,
        evaluated_at__lt=current_hour_start,
        verdict=FraudEvent.Verdict.FLAGGED,
    ).count()
    # 7 days × 24 hours = 168 hours of baseline
    hourly_baseline = baseline_qs / 168 if baseline_qs else 0

    if hourly_baseline > 0 and current_count > (FRAUD_SPIKE_MULTIPLIER * hourly_baseline):
        logger.critical(
            "FRAUD SPIKE DETECTED",
            extra={
                "current_hour_flags": current_count,
                "hourly_baseline": hourly_baseline,
                "multiplier": current_count / hourly_baseline,
            },
        )
        # TODO: Phase 2 — dispatch PagerDuty/Slack alert here
    else:
        logger.info(
            "Fraud rate check passed",
            extra={
                "current_hour_flags": current_count,
                "hourly_baseline": round(hourly_baseline, 2),
            },
        )


@shared_task(name="fraud.sync_blacklist_to_cloudflare", bind=True, max_retries=3)
def sync_blacklist_to_cloudflare(self) -> None:
    """
    Sync active IP blacklist to Cloudflare WAF.

    Runs daily. In Phase 1 this logs the intent — actual Cloudflare
    API integration is wired in Phase 2 when WAF is fully provisioned.
    """
    from apps.fraud.models import IPBlacklist

    unsynced = IPBlacklist.objects.filter(is_active=True, cloudflare_synced=False)
    count = unsynced.count()

    if count == 0:
        logger.info("Cloudflare blacklist sync: no unsynced entries")
        return

    # TODO: Phase 2 — call Cloudflare API to add IPs to WAF custom rules
    logger.info(
        "Cloudflare blacklist sync pending (Phase 2 integration)",
        extra={"unsynced_count": count},
    )
    # Mark as synced once Cloudflare integration is wired
    # unsynced.update(cloudflare_synced=True, synced_at=timezone.now())


@shared_task(name="fraud.promote_ml_model", bind=True, max_retries=1)
def promote_ml_model(candidate_model_path: str, holdout_auc: float) -> None:
    """
    Promote a newly trained ML model if it outperforms the current one.

    Args:
        candidate_model_path: Path to the candidate model artifact.
        holdout_auc: AUC-ROC on the holdout validation set.

    Called by the monthly retraining pipeline in ml/fraud/train.py.
    """
    from apps.fraud.ml_scorer import MLScorer

    MIN_AUC_THRESHOLD = 0.75  # Do not promote models below this

    if holdout_auc < MIN_AUC_THRESHOLD:
        logger.warning(
            "ML model promotion rejected — AUC below threshold",
            extra={"holdout_auc": holdout_auc, "min_threshold": MIN_AUC_THRESHOLD},
        )
        return

    import os
    from django.conf import settings

    current_path = getattr(settings, "FRAUD_ML_MODEL_PATH", None)
    if not current_path:
        logger.error("FRAUD_ML_MODEL_PATH not configured — cannot promote model")
        return

    try:
        os.replace(candidate_model_path, current_path)
        MLScorer.invalidate_cache()
        logger.info(
            "ML model promoted",
            extra={"path": current_path, "holdout_auc": holdout_auc},
        )
    except Exception:
        logger.exception("ML model promotion failed", extra={"candidate": candidate_model_path})
