"""
apps/escrow/tasks.py

Celery tasks for the Lingi7 escrow system.

Tasks
-----
daily_reconciliation        Run nightly; verifies escrow balance integrity.
auto_confirm_delivered      After 7-day window; marks escrow DELIVERED.

Scheduling (defined in config/celery.py beat_schedule):
    daily_reconciliation:   00:05 UTC daily
    auto_confirm_delivered: Every 30 minutes (polls for eligible accounts)
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from celery import shared_task
from django.db import models
from django.db.models import Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

# Buyer auto-confirm window in days (configurable via settings in Phase 2)
AUTO_CONFIRM_DAYS = 7


@shared_task(
    bind=True,
    name="escrow.daily_reconciliation",
    max_retries=1,
    default_retry_delay=300,  # 5 min retry on unexpected failure
)
def daily_reconciliation(self) -> dict:
    """
    Nightly reconciliation task.

    Algorithm:
    1. For every non-terminal EscrowAccount, sum LedgerEntry DEBIT amounts
       and subtract LedgerEntry CREDIT amounts to derive the expected balance.
    2. Compare against EscrowAccount.balance.
    3. Flag any discrepancies and write a ReconciliationLog row.
    4. If discrepancies found, trigger alert (Sentry + logger CRITICAL).

    Returns:
        dict with status, accounts_checked, discrepancy_count, run_at.
    """
    # Avoid circular import at module level
    from apps.escrow.models import (
        EscrowAccount,
        LedgerEntry,
        ReconciliationLog,
    )
    from apps.escrow.exceptions import ReconciliationError
    from apps.escrow.state_machine import EscrowState

    run_at = timezone.now()
    discrepancies = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    total_balance = Decimal("0.00")

    logger.info("Reconciliation task started at %s", run_at)

    try:
        # Only check live accounts (RELEASED and REFUNDED have zero balance by design)
        active_states = list(EscrowState.ALL - EscrowState.TERMINAL)
        accounts = EscrowAccount.objects.filter(state__in=active_states)
        accounts_checked = len(accounts)

        for account in accounts:
            # Two separate aggregates — clean and unambiguous per-account
            debit_agg = LedgerEntry.objects.filter(
                account=account,
                entry_type=LedgerEntry.EntryType.DEBIT,
            ).aggregate(total=Sum("amount"))
            credit_agg = LedgerEntry.objects.filter(
                account=account,
                entry_type=LedgerEntry.EntryType.CREDIT,
            ).aggregate(total=Sum("amount"))

            debit_sum = debit_agg["total"] or Decimal("0.00")
            credit_sum = credit_agg["total"] or Decimal("0.00")
            expected_balance = debit_sum - credit_sum

            total_debit += debit_sum
            total_credit += credit_sum
            total_balance += account.balance

            if expected_balance != account.balance:
                delta = account.balance - expected_balance
                discrepancies.append({
                    "account_id": str(account.id),
                    "order_ref": str(account.order_ref),
                    "expected_balance": str(expected_balance),
                    "actual_balance": str(account.balance),
                    "delta": str(delta),
                })
                logger.critical(
                    "RECONCILIATION DISCREPANCY: account=%s expected=ZMW %s actual=ZMW %s delta=ZMW %s",
                    account.id, expected_balance, account.balance, delta,
                )
                
        discrepancy_detected = len(discrepancies) > 0
        status = "FAIL" if discrepancy_detected else "PASS"

        log = ReconciliationLog.objects.create(
            total_accounts_checked=accounts_checked,
            ledger_debit_total=total_debit,
            ledger_credit_total=total_credit,
            account_balance_total=total_balance,
            discrepancy_amount=sum(
                abs(Decimal(d["delta"])) for d in discrepancies
            ) if discrepancies else Decimal("0.00"),
            discrepancy_detected=discrepancy_detected,
            discrepancy_details=discrepancies,
            status=status,
        )

        if discrepancy_detected:
            # Trigger Sentry alert in production (captured as unhandled exception)
            try:
                import sentry_sdk
                sentry_sdk.capture_message(
                    f"[P0] Escrow reconciliation discrepancy detected: "
                    f"{len(discrepancies)} account(s) affected. "
                    f"ReconciliationLog id={log.id}",
                    level="critical",
                )
            except Exception:  # noqa: BLE001
                pass  # Sentry not configured in dev — already logged above

        logger.info(
            "Reconciliation complete: status=%s accounts=%d discrepancies=%d",
            status,
            accounts_checked,
            len(discrepancies),
        )

        return {
            "status": status,
            "accounts_checked": accounts_checked,
            "discrepancy_count": len(discrepancies),
            "run_at": run_at.isoformat(),
            "log_id": str(log.id),
        }

    except Exception as exc:
        logger.exception("Reconciliation task failed with unexpected error: %s", exc)
        try:
            from apps.escrow.models import ReconciliationLog
            ReconciliationLog.objects.create(
                status="FAIL",
                error_message=str(exc),
            )
        except Exception:  # noqa: BLE001
            pass
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name="escrow.stale_freeze_alert",
    max_retries=1,
)
def stale_freeze_alert(self) -> dict:
    """
    Periodic task: alert on accounts stuck in FROZEN state for >48 hours.

    Frozen accounts represent locked funds that need manual review.
    Without this alert, they become invisible liabilities.

    Returns:
        dict with stale_count, oldest_freeze_hours, run_at.
    """
    from apps.escrow.models import EscrowAccount
    from apps.escrow.state_machine import EscrowState

    threshold = timezone.now() - timezone.timedelta(hours=48)

    stale_accounts = list(
        EscrowAccount.objects.filter(
            state=EscrowState.FROZEN,
            frozen_at__lt=threshold,
        ).values_list("id", "frozen_at", "balance", "order_ref")
    )

    if stale_accounts:
        oldest_hours = max(
            (timezone.now() - fz[1]).total_seconds() / 3600 for fz in stale_accounts
        )
        total_frozen = sum(fz[2] for fz in stale_accounts)
        logger.warning(
            "STALE FREEZE ALERT: %d account(s) frozen for >48h. "
            "Total frozen funds: ZMW %s. Oldest: %.0f hours.",
            len(stale_accounts), total_frozen, oldest_hours,
        )
        try:
            import sentry_sdk
            sentry_sdk.capture_message(
                f"[P1] {len(stale_accounts)} escrow account(s) frozen >48h. "
                f"Total: ZMW {total_frozen}.",
                level="warning",
            )
        except Exception:  # noqa: BLE001
            pass
    else:
        logger.debug("No stale frozen accounts detected.")

    return {
        "stale_count": len(stale_accounts),
        "run_at": timezone.now().isoformat(),
    }


@shared_task(
    bind=True,
    name="escrow.auto_confirm_delivered",
    max_retries=3,
    default_retry_delay=60,
)
def auto_confirm_delivered(self) -> dict:
    """
    Polls for IN_TRANSIT escrow accounts where the buyer has not
    confirmed delivery within AUTO_CONFIRM_DAYS days, then
    automatically marks them DELIVERED.

    The 7-day timer starts from the moment the account entered
    IN_TRANSIT state (updated_at is used as the proxy).

    This runs every 30 minutes. Only accounts with
    updated_at <= (now - 7 days) are processed.

    Uses Redis SETNX lock per account to prevent double-processing
    if the beat interval overlaps with a slow run.

    Returns:
        dict with confirmed_count, skipped_count, run_at.
    """
    from django.core.cache import cache
    from apps.escrow.models import EscrowAccount
    from apps.escrow.services import EscrowService
    from apps.escrow.state_machine import EscrowState
    from apps.escrow.exceptions import EscrowError

    cutoff = timezone.now() - timezone.timedelta(days=AUTO_CONFIRM_DAYS)

    eligible = EscrowAccount.objects.filter(
        state=EscrowState.IN_TRANSIT,
        updated_at__lte=cutoff,
    )

    confirmed = 0
    skipped = 0
    errors = 0

    for account in eligible:
        lock_key = f"escrow:auto_confirm:{account.id}"
        if not cache.add(lock_key, "1", timeout=3600):
            skipped += 1
            continue

        try:
            EscrowService.mark_delivered(
                account_id=account.id,
                notes=f"Auto-confirmed after {AUTO_CONFIRM_DAYS}-day window",
            )
            confirmed += 1
            logger.info("Auto-confirmed delivery for account=%s", account.id)
        except EscrowError as exc:
            errors += 1
            logger.warning("Auto-confirm failed for account=%s: %s", account.id, exc)
        finally:
            cache.delete(lock_key)

    logger.info(
        "auto_confirm_delivered: confirmed=%d skipped=%d errors=%d cutoff=%s",
        confirmed, skipped, errors, cutoff.isoformat(),
    )
    return {
        "confirmed_count": confirmed,
        "skipped_count": skipped,
        "error_count": errors,
        "run_at": timezone.now().isoformat(),
    }

def run_reconciliation_sync() -> dict:
    """
    Synchronous version for testing — bypasses Celery worker entirely.
    Call this directly in tests instead of daily_reconciliation.apply().get()
    """
    from apps.escrow.models import EscrowAccount, LedgerEntry, ReconciliationLog
    from apps.escrow.state_machine import EscrowState
    from django.db.models import Sum

    run_at = timezone.now()
    discrepancies = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    total_balance = Decimal("0.00")

    active_states = list(EscrowState.ALL - EscrowState.TERMINAL)
    accounts = list(EscrowAccount.objects.filter(state__in=active_states))
    accounts_checked = len(accounts)

    for account in accounts:
        debit_sum = LedgerEntry.objects.filter(
            account=account, entry_type=LedgerEntry.EntryType.DEBIT
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        credit_sum = LedgerEntry.objects.filter(
            account=account, entry_type=LedgerEntry.EntryType.CREDIT
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        expected_balance = debit_sum - credit_sum
        total_debit += debit_sum
        total_credit += credit_sum
        total_balance += account.balance

        if expected_balance != account.balance:
            delta = account.balance - expected_balance
            discrepancies.append({
                "account_id": str(account.id),
                "order_ref": str(account.order_ref),
                "expected_balance": str(expected_balance),
                "actual_balance": str(account.balance),
                "delta": str(delta),
            })

    discrepancy_detected = bool(discrepancies)
    status = "FAIL" if discrepancy_detected else "PASS"

    log = ReconciliationLog.objects.create(
        total_accounts_checked=accounts_checked,
        ledger_debit_total=total_debit,
        ledger_credit_total=total_credit,
        account_balance_total=total_balance,
        discrepancy_amount=sum(
            abs(Decimal(d["delta"])) for d in discrepancies
        ) if discrepancies else Decimal("0.00"),
        discrepancy_detected=discrepancy_detected,
        discrepancy_details=discrepancies,
        status=status,
    )

    if discrepancy_detected:
        try:
            import sentry_sdk
            sentry_sdk.capture_message(
                f"[P0] Escrow reconciliation discrepancy detected: "
                f"{len(discrepancies)} account(s). Log id={log.id}",
                level="critical",
            )
        except Exception:
            pass

    return {
        "status": status,
        "accounts_checked": accounts_checked,
        "discrepancy_count": len(discrepancies),
        "run_at": run_at.isoformat(),
        "log_id": str(log.id),
    }