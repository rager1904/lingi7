"""
apps/admin_audit/signals.py
============================
Django signal receivers that automatically capture every admin
create / update / delete across all models on the platform.

How it works
------------
1.  ``AuditMiddleware`` (see middleware.py) attaches the current request
    object to a thread-local so signal handlers can read IP/UA/session
    without needing the request passed explicitly.

2.  ``post_save`` receiver fires after every model save.  We detect
    CREATE vs UPDATE via the ``created`` flag and delegate to AuditService.

3.  ``pre_save`` receiver fires BEFORE every model save to capture the
    ``before_state`` snapshot for UPDATE operations.

4.  ``post_delete`` receiver fires after every model delete and logs the
    final snapshot (already captured in pre_delete).

5.  The ``AUDIT_EXCLUDED_MODELS`` set prevents log-storm self-referential
    entries (AdminAuditLog itself) and noisy Django internals.

Thread-safety
-------------
State snapshots for UPDATE are stored in a per-signal ``_audit_before``
dict keyed by ``(app_label, model_name, pk)``.  This avoids cross-request
contamination while handling concurrent requests.

Signal registration
-------------------
Signals are connected in ``apps.py`` via ``AppConfig.ready()`` to ensure
they are registered exactly once at startup.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Type

from django.db import connection, models
from django.db.models.signals import post_delete, post_save, pre_save

from .services import AuditService, _serialize_instance

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thread-local request storage (populated by AuditMiddleware)
# ---------------------------------------------------------------------------

_local = threading.local()


def get_current_request() -> Any | None:
    """Return the request object stashed by AuditMiddleware for this thread.

    Returns:
        Django HttpRequest or None if no request is in progress (e.g. Celery).
    """
    return getattr(_local, "request", None)


def set_current_request(request: Any | None) -> None:
    """Store the request on the thread-local (called by AuditMiddleware).

    Args:
        request: Django HttpRequest or None.
    """
    _local.request = request


# ---------------------------------------------------------------------------
# Models excluded from audit logging
# ---------------------------------------------------------------------------

# fmt: off
AUDIT_EXCLUDED_MODELS: frozenset[str] = frozenset({
    # Self-referential — would cause infinite recursion
    "admin_audit.adminauditlog",
    # Django internals — high-volume, low-value for audit purposes
    "sessions.session",
    "contenttypes.contenttype",
    "admin.logentry",
    # Celery / Django-Q task tables
    "django_celery_beat.periodictask",
    "django_celery_beat.clockedschedule",
    "django_celery_beat.crontabschedule",
    "django_celery_beat.intervalschedule",
    "django_celery_beat.solarschedule",
    "django_celery_results.taskresult",
})
# fmt: on


def _model_label(sender: Type[models.Model]) -> str:
    """Return ``"app_label.model_name"`` for *sender*.

    Args:
        sender: A Django model class.

    Returns:
        Dot-notation label string.
    """
    return f"{sender._meta.app_label}.{sender._meta.model_name}"


def _should_audit(sender: Type[models.Model]) -> bool:
    """Return True if this model should be audited.

    Args:
        sender: A Django model class.

    Returns:
        False if the model is in the exclusion set; True otherwise.
    """
    return _model_label(sender) not in AUDIT_EXCLUDED_MODELS


def _table_exists(table_name: str) -> bool:
    """Check if a database table exists without raising an exception.

    This is used to skip audit operations during migrations before tables
    are created.

    Args:
        table_name: Name of the table to check (e.g., 'admin_audit_adminauditlog').

    Returns:
        True if the table exists in the current database; False otherwise.
    """
    with connection.cursor() as cursor:
        return table_name in connection.introspection.table_names(cursor)


# ---------------------------------------------------------------------------
# Before-state cache (keyed by (app_label, model_name, pk))
# ---------------------------------------------------------------------------

# Use thread-local dict to avoid cross-request contamination
def _get_before_cache() -> dict[tuple[str, str, Any], dict[str, Any]]:
    if not hasattr(_local, "before_cache"):
        _local.before_cache = {}
    return _local.before_cache


# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------


def _handle_pre_save(
    sender: Type[models.Model],
    instance: Any,
    **kwargs: Any,
) -> None:
    """Capture before-state for UPDATE operations.

    Fires BEFORE save.  If the instance already has a PK and exists in the
    database, serialise its current DB state and stash it in the thread-local
    before-cache.  The post_save handler will retrieve this snapshot.

    Args:
        sender: Model class that sent the signal.
        instance: The model instance about to be saved.
        **kwargs: Additional signal keyword arguments.
    """
    if not _should_audit(sender):
        return

    # Only capture before-state for existing (UPDATE) operations
    if instance.pk is None:
        return

    try:
        db_instance = sender.objects.get(pk=instance.pk)
        cache_key = (sender._meta.app_label, sender._meta.model_name, instance.pk)
        _get_before_cache()[cache_key] = _serialize_instance(db_instance)
    except sender.DoesNotExist:
        # Race condition: record was deleted between pre_save and post_save.
        # Treat as CREATE in post_save.
        pass
    except Exception as exc:  # pragma: no cover
        # Skip errors during migrations (table may not exist yet)
        if "does not exist" in str(exc).lower():
            return
        logger.warning(
            "audit.pre_save.error | %s:%s | %s",
            _model_label(sender),
            instance.pk,
            exc,
        )


def _handle_post_save(
    sender: Type[models.Model],
    instance: Any,
    created: bool,
    **kwargs: Any,
) -> None:
    """Write CREATE or UPDATE audit entry after a successful save.

    Args:
        sender: Model class that sent the signal.
        instance: The model instance that was saved.
        created: True if this was an INSERT (new row), False for UPDATE.
        **kwargs: Additional signal keyword arguments.
    """
    if not _should_audit(sender):
        return

    # Skip if the audit log table doesn't exist yet (during migrations)
    if not _table_exists("admin_audit_adminauditlog"):
        return

    request = get_current_request()
    actor = getattr(request, "user", None) if request else None

    # Normalise anonymous / unauthenticated users to None
    if actor is not None and not getattr(actor, "is_authenticated", False):
        actor = None

    try:
        if created:
            AuditService.log_create(instance=instance, actor=actor, request=request)
        else:
            cache_key = (sender._meta.app_label, sender._meta.model_name, instance.pk)
            before = _get_before_cache().pop(cache_key, None)
            if before is not None:
                AuditService.log_update(
                    instance=instance,
                    actor=actor,
                    before_state=before,
                    request=request,
                )
            # If before is None it means pre_save didn't find the DB record —
            # this is an upsert-style creation.  Log as CREATE.
            else:
                AuditService.log_create(instance=instance, actor=actor, request=request)
    except Exception as exc:  # pragma: no cover
        # Skip errors during migrations (table may not exist yet)
        if "does not exist" in str(exc).lower():
            return
        # Never let audit failures bubble up and break the main transaction.
        logger.error(
            "audit.post_save.error | %s:%s | created=%s | %s",
            _model_label(sender),
            instance.pk,
            created,
            exc,
            exc_info=True,
        )


def _handle_post_delete(
    sender: Type[models.Model],
    instance: Any,
    **kwargs: Any,
) -> None:
    """Write DELETE audit entry after a successful deletion.

    Args:
        sender: Model class that sent the signal.
        instance: The model instance that was deleted (in-memory only at this point).
        **kwargs: Additional signal keyword arguments.
    """
    if not _should_audit(sender):
        return

    # Skip if the audit log table doesn't exist yet (during migrations)
    if not _table_exists("admin_audit_adminauditlog"):
        return

    request = get_current_request()
    actor = getattr(request, "user", None) if request else None

    if actor is not None and not getattr(actor, "is_authenticated", False):
        actor = None

    # Retrieve before-state if pre_save/pre_delete stashed it; otherwise
    # serialise the in-memory instance (fields are still populated post-delete).
    cache_key = (sender._meta.app_label, sender._meta.model_name, instance.pk)
    before = _get_before_cache().pop(cache_key, None)

    try:
        AuditService.log_delete(
            instance=instance,
            actor=actor,
            before_state=before,
            request=request,
        )
    except Exception as exc:  # pragma: no cover
        # Skip errors during migrations (table may not exist yet)
        if "does not exist" in str(exc).lower():
            return
        logger.error(
            "audit.post_delete.error | %s:%s | %s",
            _model_label(sender),
            instance.pk,
            exc,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Signal connection (called from AppConfig.ready())
# ---------------------------------------------------------------------------


def connect_audit_signals() -> None:
    """Connect all audit signal receivers to Django's signal dispatcher.

    This function is idempotent — calling it multiple times is safe because
    Django deduplicates by ``dispatch_uid``.

    Called from ``AdminAuditConfig.ready()`` in apps.py.
    """
    pre_save.connect(
        _handle_pre_save,
        dispatch_uid="admin_audit.pre_save",
    )
    post_save.connect(
        _handle_post_save,
        dispatch_uid="admin_audit.post_save",
    )
    post_delete.connect(
        _handle_post_delete,
        dispatch_uid="admin_audit.post_delete",
    )
    logger.info("admin_audit: signal receivers connected.")
