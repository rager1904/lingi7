"""
apps/admin_audit/apps.py
========================
AppConfig for the admin_audit application.

``ready()`` is the correct Django hook for connecting signals — it fires
once after all apps and models are fully loaded.  Connecting signals here
guarantees:

1.  Signals are registered exactly once (no duplicate receivers).
2.  All model classes referenced in signal handlers are already imported.
3.  The audit app is active before any admin action can be performed.
"""

from __future__ import annotations

from django.apps import AppConfig


class AdminAuditConfig(AppConfig):
    """Configuration for the admin_audit Django application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.admin_audit"
    verbose_name = "Admin Audit Trail"

    def ready(self) -> None:
        """Connect audit signal receivers when Django starts up.

        This is called once after the application registry is fully populated.
        """
        from .signals import connect_audit_signals  # noqa: PLC0415

        connect_audit_signals()
