"""
apps/admin_audit/admin.py
=========================
Read-only Django admin interface for AdminAuditLog.

Design constraints:
* No add / change / delete permissions — this is a forensic read interface only.
* All fields are read-only in the detail view.
* Rich list display with filters for actor, action type, target model, and date.
* before/after state rendered as formatted JSON for human readability.
* Zambian compliance: admin access to audit logs is itself logged (Django's
  own LogEntry handles this for admin interface access).
"""

from __future__ import annotations

import json

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import AdminAuditLog


@admin.register(AdminAuditLog)
class AdminAuditLogAdmin(admin.ModelAdmin):
    """Read-only admin view of the immutable audit trail.

    Provides:
    - Rich list display with colour-coded action types
    - Full-text search on actor email, target type, and target repr
    - Date-hierarchy drill-down for compliance review
    - Pretty-printed JSON diff viewer for before/after state
    """

    # ------------------------------------------------------------------
    # List view
    # ------------------------------------------------------------------

    list_display = (
        "timestamp",
        "coloured_action",
        "actor_email",
        "target_content_type",
        "target_object_id",
        "truncated_repr",
        "ip_address",
    )
    list_filter = (
        "action_type",
        "target_content_type",
        ("timestamp", admin.DateFieldListFilter),
    )
    search_fields = (
        "actor_email",
        "target_content_type",
        "target_object_id",
        "target_repr",
        "ip_address",
    )
    date_hierarchy = "timestamp"
    ordering = ("-timestamp",)

    # ------------------------------------------------------------------
    # Detail view
    # ------------------------------------------------------------------

    readonly_fields = (
        "id",
        "actor",
        "actor_email",
        "coloured_action",
        "target_content_type",
        "target_object_id",
        "target_repr",
        "formatted_before_state",
        "formatted_after_state",
        "ip_address",
        "user_agent",
        "session_key",
        "timestamp",
    )

    fieldsets = (
        (
            "Event",
            {
                "fields": (
                    "id",
                    "timestamp",
                    "coloured_action",
                    "ip_address",
                    "user_agent",
                    "session_key",
                )
            },
        ),
        (
            "Actor",
            {"fields": ("actor", "actor_email")},
        ),
        (
            "Target",
            {
                "fields": (
                    "target_content_type",
                    "target_object_id",
                    "target_repr",
                )
            },
        ),
        (
            "State Diff",
            {
                "fields": ("formatted_before_state", "formatted_after_state"),
                "classes": ("wide",),
            },
        ),
    )

    # ------------------------------------------------------------------
    # Permission overrides — strictly read-only
    # ------------------------------------------------------------------

    def has_add_permission(self, request: object) -> bool:  # type: ignore[override]
        return False

    def has_change_permission(  # type: ignore[override]
        self,
        request: object,
        obj: AdminAuditLog | None = None,
    ) -> bool:
        return False

    def has_delete_permission(  # type: ignore[override]
        self,
        request: object,
        obj: AdminAuditLog | None = None,
    ) -> bool:
        return False

    # ------------------------------------------------------------------
    # Custom display methods
    # ------------------------------------------------------------------

    @admin.display(description="Action")
    def coloured_action(self, obj: AdminAuditLog) -> str:
        """Render action type with colour coding for quick visual scanning."""
        colours = {
            "CREATE": "#1a7f37",   # green
            "UPDATE": "#0550ae",   # blue
            "DELETE": "#cf222e",   # red
            "SOFT_DELETE": "#9a6700",  # amber
            "RESTORE": "#6f42c1",  # purple
        }
        colour = colours.get(obj.action_type, "#57606a")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colour,
            obj.get_action_type_display(),
        )

    @admin.display(description="Target repr")
    def truncated_repr(self, obj: AdminAuditLog) -> str:
        """Truncate long target_repr for the list view."""
        return (obj.target_repr[:80] + "…") if len(obj.target_repr) > 80 else obj.target_repr

    @admin.display(description="Before state")
    def formatted_before_state(self, obj: AdminAuditLog) -> str:
        """Render before_state as indented JSON in a <pre> block."""
        return self._format_json(obj.before_state)

    @admin.display(description="After state")
    def formatted_after_state(self, obj: AdminAuditLog) -> str:
        """Render after_state as indented JSON in a <pre> block."""
        return self._format_json(obj.after_state)

    @staticmethod
    def _format_json(data: dict | None) -> str:
        if data is None:
            return mark_safe('<em style="color: #57606a;">— (null)</em>')
        formatted = json.dumps(data, indent=2, default=str)
        return format_html(
            '<pre style="background:#f6f8fa; padding:12px; border-radius:6px; '
            'font-size:12px; max-height:400px; overflow:auto; white-space:pre-wrap;">'
            "{}"
            "</pre>",
            formatted,
        )
