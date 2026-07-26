"""
Notifications Admin — apps/notifications/admin.py

Read-only audit view of all notification logs.
Admins can view and filter but cannot edit or delete records.

Document Ref: LG7-BE-012
"""

from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

from .models import NotificationLog, NotificationStatus


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    """Read-only admin for NotificationLog.

    Provides filtering by channel, event type, and status.
    Useful for debugging delivery failures and proving audit trail.
    """

    list_display = [
        "id_short",
        "channel",
        "event_type",
        "recipient_address",
        "status_badge",
        "attempt_count",
        "created_at",
        "sent_at",
    ]

    list_filter = ["channel", "status", "event_type", "created_at"]
    search_fields = [
        "recipient_address",
        "related_object_id",
        "provider_ref",
        "recipient__phone_number",
    ]
    readonly_fields = [
        "id",
        "recipient",
        "channel",
        "event_type",
        "recipient_address",
        "subject",
        "body_plain",
        "body_html",
        "status",
        "provider_ref",
        "error_message",
        "attempt_count",
        "context_data",
        "related_object_id",
        "related_object_type",
        "created_at",
        "sent_at",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"

    def id_short(self, obj: NotificationLog) -> str:
        """Display truncated UUID for readability."""
        return str(obj.id)[:8] + "..."

    id_short.short_description = "ID"

    def status_badge(self, obj: NotificationLog) -> str:
        """Colour-coded status badge."""
        colours = {
            NotificationStatus.SENT: "#27ae60",
            NotificationStatus.DELIVERED: "#2980b9",
            NotificationStatus.FAILED: "#e74c3c",
            NotificationStatus.RETRYING: "#f39c12",
            NotificationStatus.PENDING: "#95a5a6",
        }
        colour = colours.get(obj.status, "#95a5a6")
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; '
            'border-radius:3px; font-size:11px;">{}</span>',
            colour,
            obj.status,
        )

    status_badge.short_description = "Status"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
