"""
Dispute Serializers — apps/disputes/serializers.py
"""

from rest_framework import serializers

from .models import Dispute, DisputeEvent, Evidence


class EvidenceSerializer(serializers.ModelSerializer):
    """Read serializer for evidence items."""

    submitted_by_email = serializers.EmailField(
        source="submitted_by_user.email", read_only=True
    )

    class Meta:
        model = Evidence
        fields = [
            "id",
            "dispute",
            "submitted_by_email",
            "submitted_by_role",
            "evidence_type",
            "description",
            "file",
            "created_at",
        ]
        read_only_fields = fields


class EvidenceCreateSerializer(serializers.ModelSerializer):
    """Write serializer for evidence submission."""

    class Meta:
        model = Evidence
        fields = ["evidence_type", "description", "file"]

    def validate(self, data: dict) -> dict:
        if (
            data.get("evidence_type") != Evidence.EvidenceType.TEXT
            and not data.get("file")
        ):
            raise serializers.ValidationError(
                {"file": "A file is required for non-text evidence types."}
            )
        return data


class DisputeEventSerializer(serializers.ModelSerializer):
    """Read-only serializer for dispute audit trail."""

    actor_email = serializers.EmailField(source="actor.email", read_only=True)

    class Meta:
        model = DisputeEvent
        fields = [
            "id",
            "actor_email",
            "action",
            "before_status",
            "after_status",
            "notes",
            "created_at",
        ]
        read_only_fields = fields


class DisputeCreateSerializer(serializers.ModelSerializer):
    """Buyer-facing serializer for raising a dispute."""

    class Meta:
        model = Dispute
        fields = ["order", "reason", "description"]

    def validate_reason(self, value: str) -> str:
        valid = [c[0] for c in Dispute.Reason.choices]
        if value not in valid:
            raise serializers.ValidationError(
                f"Invalid reason. Must be one of: {', '.join(valid)}"
            )
        return value


class DisputeListSerializer(serializers.ModelSerializer):
    """Compact serializer for dispute list views."""

    order_reference = serializers.CharField(source="order.reference", read_only=True)
    raised_by_email = serializers.EmailField(source="raised_by.email", read_only=True)

    class Meta:
        model = Dispute
        fields = [
            "id",
            "order_reference",
            "raised_by_email",
            "reason",
            "status",
            "sla_deadline",
            "created_at",
        ]
        read_only_fields = fields


class DisputeDetailSerializer(serializers.ModelSerializer):
    """Full detail serializer including evidence and event trail."""

    evidence = EvidenceSerializer(many=True, read_only=True)
    events = DisputeEventSerializer(many=True, read_only=True)
    order_reference = serializers.CharField(source="order.reference", read_only=True)
    raised_by_email = serializers.EmailField(source="raised_by.email", read_only=True)
    assigned_to_email = serializers.EmailField(
        source="assigned_to.email", read_only=True, allow_null=True
    )
    resolved_by_email = serializers.EmailField(
        source="resolved_by.email", read_only=True, allow_null=True
    )
    is_sla_breached = serializers.BooleanField(read_only=True)

    class Meta:
        model = Dispute
        fields = [
            "id",
            "order_reference",
            "escrow_account",
            "raised_by_email",
            "assigned_to_email",
            "resolved_by_email",
            "reason",
            "description",
            "status",
            "resolution_notes",
            "refund_amount",
            "sla_deadline",
            "is_sla_breached",
            "resolved_at",
            "created_at",
            "updated_at",
            "evidence",
            "events",
        ]
        read_only_fields = fields


class DisputeResolveSerializer(serializers.Serializer):
    """Admin serializer for resolving a dispute."""

    resolution_notes = serializers.CharField(min_length=20)
    refund_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
