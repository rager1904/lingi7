"""
apps/escrow/serializers.py

Read-only serializers for the escrow API endpoints.
Write operations are never accepted via serializer — all mutations
go through EscrowService methods exclusively.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.escrow.models import (
    EscrowAccount,
    EscrowHold,
    FraudGateLog,
    LedgerEntry,
    ReconciliationLog,
)


class LedgerEntrySerializer(serializers.ModelSerializer):
    """Read-only representation of a single ledger entry."""

    class Meta:
        model = LedgerEntry
        fields = [
            "id",
            "entry_type",
            "amount",
            "description",
            "operation_ref",
            "balance_after",
            "created_at",
        ]
        read_only_fields = fields


class EscrowHoldSerializer(serializers.ModelSerializer):
    """Read-only payment reference details linked to an EscrowAccount."""

    class Meta:
        model = EscrowHold
        fields = [
            "id",
            "collection_ref",
            "disbursement_ref",
            "payment_provider",
            "gross_amount",
            "fee_amount",
            "net_amount",
            "created_at",
        ]
        read_only_fields = fields


class FraudGateLogSerializer(serializers.ModelSerializer):
    """Read-only fraud gate evaluation record."""

    class Meta:
        model = FraudGateLog
        fields = [
            "id",
            "rule_flags",
            "ml_risk_score",
            "verdict",
            "freeze_reason",
            "created_at",
            "reviewed_by_ref",
            "reviewed_at",
        ]
        read_only_fields = fields


class EscrowAccountSerializer(serializers.ModelSerializer):
    """
    Detailed read-only view of an EscrowAccount including its ledger
    entries, hold record, and fraud gate history.

    Used by staff ViewSet only — never exposed to buyers or vendors
    without appropriate field filtering.
    """

    ledger_entries = LedgerEntrySerializer(many=True, read_only=True)
    hold = EscrowHoldSerializer(read_only=True)
    fraud_gate_logs = FraudGateLogSerializer(many=True, read_only=True)

    class Meta:
        model = EscrowAccount
        fields = [
            "id",
            "order_ref",
            "buyer_ref",
            "vendor_ref",
            "state",
            "balance",
            "currency",
            "created_at",
            "updated_at",
            "released_at",
            "frozen_at",
            "notes",
            "hold",
            "ledger_entries",
            "fraud_gate_logs",
        ]
        read_only_fields = fields


class EscrowAccountListSerializer(serializers.ModelSerializer):
    """
    Lightweight list serializer — no nested relations.
    Used for paginated admin list views.
    """

    class Meta:
        model = EscrowAccount
        fields = [
            "id",
            "order_ref",
            "state",
            "balance",
            "currency",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ReconciliationLogSerializer(serializers.ModelSerializer):
    """Read-only nightly reconciliation run result."""

    class Meta:
        model = ReconciliationLog
        fields = [
            "id",
            "run_at",
            "total_accounts_checked",
            "ledger_debit_total",
            "ledger_credit_total",
            "account_balance_total",
            "discrepancy_amount",
            "discrepancy_detected",
            "discrepancy_details",
            "status",
            "error_message",
        ]
        read_only_fields = fields
