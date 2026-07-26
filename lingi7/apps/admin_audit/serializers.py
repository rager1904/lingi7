"""
apps/admin_audit/serializers.py
================================
DRF serializers for the AdminAuditLog model.

Only read serializers are provided — the audit log is write-via-service-only.
"""

from __future__ import annotations

from rest_framework import serializers

from .models import AdminAuditLog


class AdminAuditLogSerializer(serializers.ModelSerializer):
    """Full read serializer for AdminAuditLog.

    Intended for internal admin API endpoints only.
    Not exposed to buyer/vendor roles.
    """

    action_type_display = serializers.CharField(
        source="get_action_type_display",
        read_only=True,
    )

    class Meta:
        model = AdminAuditLog
        fields = (
            "id",
            "actor",
            "actor_email",
            "action_type",
            "action_type_display",
            "target_content_type",
            "target_object_id",
            "target_repr",
            "before_state",
            "after_state",
            "ip_address",
            "user_agent",
            "session_key",
            "timestamp",
        )
        read_only_fields = fields


class AdminAuditLogListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list/pagination responses."""

    action_type_display = serializers.CharField(
        source="get_action_type_display",
        read_only=True,
    )

    class Meta:
        model = AdminAuditLog
        fields = (
            "id",
            "actor_email",
            "action_type",
            "action_type_display",
            "target_content_type",
            "target_object_id",
            "target_repr",
            "ip_address",
            "timestamp",
        )
        read_only_fields = fields
