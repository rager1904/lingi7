"""
apps/admin_audit/services.py
============================
AuditService — the ONLY permitted write path for AdminAuditLog.

All signals, views, and management commands must use this service.
Direct ORM writes to AdminAuditLog outside this module are prohibited.

Architecture note
-----------------
The service is intentionally synchronous.  Audit log writes happen
inside the same database transaction as the action being logged
(via Django signals).  This guarantees that either the action AND
its log entry both commit, or neither does — there is no window
in which an action is committed without a corresponding audit row.

Do NOT move log writes to Celery tasks — async writes would break
this atomicity guarantee and create gaps in the audit trail.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import transaction
from django.forms.models import model_to_dict

from .models import ActionType, AdminAuditLog

logger = logging.getLogger(__name__)


def _serialize_instance(instance: Any) -> dict[str, Any]:
    """Serialise a Django model instance to a plain dict.

    Uses ``model_to_dict`` as the base, then stringifies any non-JSON-safe
    types (UUIDs, Decimals, datetimes, etc.) to ensure the result is always
    JSON-serialisable.

    Args:
        instance: Any Django model instance.

    Returns:
        A dict representation of the instance safe for JSONField storage.
    """
    import decimal
    import uuid
    from datetime import date, datetime

    try:
        raw: dict[str, Any] = model_to_dict(instance)
    except Exception:
        # model_to_dict can fail on some edge cases — fall back to __dict__
        raw = {
            k: v
            for k, v in instance.__dict__.items()
            if not k.startswith("_")
        }

    SENSITIVE_FIELDS = {"password", "last_login"}

    def _safe(value: Any) -> Any:
        if isinstance(value, (uuid.UUID,)):
            return str(value)
        if isinstance(value, decimal.Decimal):
            return str(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if isinstance(value, dict):
            return {k: _safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_safe(v) for v in value]
        if isinstance(value, (set, frozenset)):
            return [_safe(v) for v in sorted(value, key=str)]
        return value

    return {k: _safe(v) for k, v in raw.items() if k not in SENSITIVE_FIELDS}


def _get_content_type_label(instance: Any) -> str:
    """Return a dot-notation content-type label for *instance*.

    Args:
        instance: Any Django model instance.

    Returns:
        e.g. ``"users.user"``, ``"escrow.escrowaccount"``
    """
    meta = instance._meta
    return f"{meta.app_label}.{meta.model_name}"


class AuditService:
    """Stateless service for writing immutable audit log entries.

    All methods are classmethods — instantiation is not required.

    Usage::

        AuditService.log_create(instance=order, actor=request.user, request=request)
        AuditService.log_update(instance=escrow, actor=request.user,
                                 before_state=before, request=request)
        AuditService.log_delete(instance=user, actor=request.user, request=request)
    """

    @classmethod
    def _extract_request_meta(
        cls,
        request: Any | None,
    ) -> dict[str, str | None]:
        """Extract IP, user agent, and session key from a Django request.

        Args:
            request: Django HttpRequest, or None if no request context exists
                     (e.g. management commands, Celery tasks).

        Returns:
            Dict with ``ip_address``, ``user_agent``, ``session_key``.
        """
        if request is None:
            return {"ip_address": None, "user_agent": "", "session_key": ""}

        # Honour reverse-proxy headers (Cloudflare sets CF-Connecting-IP)
        ip = (
            request.META.get("HTTP_CF_CONNECTING_IP")
            or request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR")
        )

        user_agent = request.META.get("HTTP_USER_AGENT", "")[:512]
        session_key = getattr(getattr(request, "session", None), "session_key", "") or ""

        return {
            "ip_address": ip or None,
            "user_agent": user_agent,
            "session_key": session_key,
        }

    @classmethod
    def _get_actor_email(cls, actor: AbstractBaseUser | None) -> str:
        """Safely extract the actor's email for denormalisation.

        Args:
            actor: The admin user, or None for system actions.

        Returns:
            The actor's email string, or ``"system"`` if no actor.
        """
        if actor is None:
            return "system"
        return getattr(actor, "email", None) or str(actor.pk)

    @classmethod
    @transaction.atomic
    def log_create(
        cls,
        *,
        instance: Any,
        actor: AbstractBaseUser | None,
        request: Any | None = None,
    ) -> AdminAuditLog:
        """Write a CREATE audit entry for *instance*.

        Args:
            instance: The newly created Django model instance.
            actor: The admin user who triggered the creation.
            request: Optional Django HttpRequest for IP/UA/session capture.

        Returns:
            The persisted AdminAuditLog row.
        """
        meta = cls._extract_request_meta(request)
        entry = AdminAuditLog(
            actor=actor,
            actor_email=cls._get_actor_email(actor),
            action_type=ActionType.CREATE,
            target_content_type=_get_content_type_label(instance),
            target_object_id=str(instance.pk),
            target_repr=str(instance)[:500],
            before_state=None,
            after_state=_serialize_instance(instance),
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
            session_key=meta["session_key"],
        )
        entry.save()
        logger.debug(
            "audit.create | %s | %s:%s",
            cls._get_actor_email(actor),
            _get_content_type_label(instance),
            instance.pk,
        )
        return entry

    @classmethod
    @transaction.atomic
    def log_update(
        cls,
        *,
        instance: Any,
        actor: AbstractBaseUser | None,
        before_state: dict[str, Any],
        request: Any | None = None,
    ) -> AdminAuditLog:
        """Write an UPDATE audit entry for *instance*.

        The caller is responsible for capturing ``before_state`` BEFORE
        performing the update.  The service captures ``after_state`` from
        the (already-saved) instance.

        Args:
            instance: The Django model instance after the update.
            actor: The admin user who triggered the update.
            before_state: Serialised state dict captured before the save.
            request: Optional Django HttpRequest.

        Returns:
            The persisted AdminAuditLog row.
        """
        meta = cls._extract_request_meta(request)
        entry = AdminAuditLog(
            actor=actor,
            actor_email=cls._get_actor_email(actor),
            action_type=ActionType.UPDATE,
            target_content_type=_get_content_type_label(instance),
            target_object_id=str(instance.pk),
            target_repr=str(instance)[:500],
            before_state=before_state,
            after_state=_serialize_instance(instance),
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
            session_key=meta["session_key"],
        )
        entry.save()
        logger.debug(
            "audit.update | %s | %s:%s",
            cls._get_actor_email(actor),
            _get_content_type_label(instance),
            instance.pk,
        )
        return entry

    @classmethod
    @transaction.atomic
    def log_delete(
        cls,
        *,
        instance: Any,
        actor: AbstractBaseUser | None,
        before_state: dict[str, Any] | None = None,
        request: Any | None = None,
    ) -> AdminAuditLog:
        """Write a DELETE audit entry for *instance*.

        Args:
            instance: The Django model instance being deleted (still in memory).
            actor: The admin user who triggered the delete.
            before_state: Optional pre-serialised state.  If None, the service
                          will attempt to serialise the in-memory instance.
            request: Optional Django HttpRequest.

        Returns:
            The persisted AdminAuditLog row.
        """
        meta = cls._extract_request_meta(request)
        snapshot = before_state if before_state is not None else _serialize_instance(instance)
        entry = AdminAuditLog(
            actor=actor,
            actor_email=cls._get_actor_email(actor),
            action_type=ActionType.DELETE,
            target_content_type=_get_content_type_label(instance),
            target_object_id=str(instance.pk),
            target_repr=str(instance)[:500],
            before_state=snapshot,
            after_state=None,
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
            session_key=meta["session_key"],
        )
        entry.save()
        logger.debug(
            "audit.delete | %s | %s:%s",
            cls._get_actor_email(actor),
            _get_content_type_label(instance),
            instance.pk,
        )
        return entry

    @classmethod
    def get_history(
        cls,
        instance: Any,
        limit: int = 100,
    ) -> "models.QuerySet[AdminAuditLog]":  # noqa: F821
        """Return the full audit history for a specific object.

        Args:
            instance: The Django model instance to look up.
            limit: Maximum number of rows to return (most recent first).

        Returns:
            QuerySet of AdminAuditLog ordered by timestamp descending.
        """
        return AdminAuditLog.objects.filter(
            target_content_type=_get_content_type_label(instance),
            target_object_id=str(instance.pk),
        ).order_by("-timestamp")[:limit]
