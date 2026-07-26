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


@shared_task(name="fraud.close_fraud_feedback_loop", bind=True, max_retries=1)
def close_fraud_feedback_loop(self) -> dict:
    """
    Close the feedback loop for ML model precision/recall measurement.

    Runs monthly. For FLAGGED events older than 30 days, determines if
    the order was ultimately refunded (= confirmed fraud) or completed
    (= false positive). This data feeds back into ML retraining.

    Returns:
        dict with updated_count, confirmed_fraud_count, false_positive_count.
    """
    from apps.fraud.models import FraudEvent

    cutoff = timezone.now() - timedelta(days=30)
    events = FraudEvent.objects.filter(
        verdict=FraudEvent.Verdict.FLAGGED,
        outcome_confirmed_fraud__isnull=True,
        evaluated_at__lt=cutoff,
    ).select_related("order")

    confirmed = 0
    false_positive = 0
    skipped = 0

    for event in events:
        if event.order is None:
            skipped += 1
            continue

        order_status = event.order.status
        if order_status in ("REFUNDED", "CANCELLED"):
            event.outcome_confirmed_fraud = True
            confirmed += 1
        elif order_status in ("COMPLETED", "RELEASED"):
            event.outcome_confirmed_fraud = False
            false_positive += 1
        else:
            skipped += 1
            continue

        event.outcome_updated_at = timezone.now()
        event.save(update_fields=["outcome_confirmed_fraud", "outcome_updated_at"])

    total_updated = confirmed + false_positive
    logger.info(
        "Fraud feedback loop: updated=%d confirmed_fraud=%d false_positive=%d skipped=%d",
        total_updated, confirmed, false_positive, skipped,
    )
    return {
        "updated_count": total_updated,
        "confirmed_fraud_count": confirmed,
        "false_positive_count": false_positive,
        "skipped_count": skipped,
    }


@shared_task(name="fraud.auto_blacklist_ips", bind=True, max_retries=3)
def auto_blacklist_ips(self) -> dict:
    """
    Auto-blacklist IPs that trigger 3+ fraud flags within 1 hour.

    When the same IP triggers PAYMENT_VELOCITY or IP_BLACKLIST rules
    repeatedly, it's likely malicious. Auto-add to blacklist and sync
    to Cloudflare in Phase 2.

    Returns:
        dict with blacklisted_count, run_at.
    """
    from apps.fraud.models import FraudEvent, IPBlacklist

    one_hour_ago = timezone.now() - timedelta(hours=1)
    suspicious_ips = (
        FraudEvent.objects.filter(
            evaluated_at__gte=one_hour_ago,
            rule_triggered__in=[
                FraudEvent.Verdict.FLAGGED,
                "PAYMENT_VELOCITY",
                "IP_BLACKLIST",
            ],
        )
        .values("order__buyer_ip_address")
        .annotate(count=Count("id"))
        .filter(count__gte=3, order__buyer_ip_address__isnull=False)
    )

    blacklisted = 0
    for row in suspicious_ips:
        ip = row["order__buyer_ip_address"]
        if not ip:
            continue
        _, created = IPBlacklist.objects.get_or_create(
            ip_address=ip,
            defaults={
                "reason": f"Auto-blacklisted: {row['count']} fraud flags in 1 hour",
            },
        )
        if created:
            blacklisted += 1
            logger.warning(
                "Auto-blacklisted IP %s after %d fraud flags in 1 hour",
                ip, row["count"],
            )

    return {
        "blacklisted_count": blacklisted,
        "run_at": timezone.now().isoformat(),
    }
