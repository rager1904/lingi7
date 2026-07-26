"""
apps/escrow/migrations/0001_initial.py

Initial migration for the escrow system.

For PostgreSQL, the escrow_ledger schema must be pre-created.
For SQLite, schemas are not supported — tables use simple names.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def _is_sqlite(apps, schema_editor):
    return schema_editor.connection.vendor == "sqlite"


def create_schema_forward(apps, schema_editor):
    if not _is_sqlite(apps, schema_editor):
        schema_editor.execute("CREATE SCHEMA IF NOT EXISTS escrow_ledger;")


def drop_schema(apps, schema_editor):
    if not _is_sqlite(apps, schema_editor):
        schema_editor.execute("DROP SCHEMA IF EXISTS escrow_ledger CASCADE;")


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.RunPython(create_schema_forward, drop_schema),
        migrations.CreateModel(
            name="EscrowAccount",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("order_ref", models.UUIDField(db_index=True, unique=True)),
                ("buyer_ref", models.UUIDField(db_index=True)),
                ("vendor_ref", models.UUIDField(blank=True, db_index=True, null=True)),
                ("state", models.CharField(
                    choices=[
                        ("PENDING", "PENDING"), ("HELD", "HELD"),
                        ("IN_TRANSIT", "IN_TRANSIT"), ("DELIVERED", "DELIVERED"),
                        ("RELEASED", "RELEASED"), ("DISPUTED", "DISPUTED"),
                        ("REFUNDED", "REFUNDED"), ("FROZEN", "FROZEN"),
                    ],
                    db_index=True,
                    default="PENDING",
                    max_length=20,
                )),
                ("balance", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("currency", models.CharField(default="ZMW", max_length=3)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("released_at", models.DateTimeField(blank=True, null=True)),
                ("frozen_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "escrow_account",
            },
        ),
        migrations.CreateModel(
            name="LedgerEntry",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("account", models.ForeignKey(
                    db_column="account_id",
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="ledger_entries",
                    to="escrow.escrowaccount",
                )),
                ("entry_type", models.CharField(
                    choices=[("DEBIT", "Debit"), ("CREDIT", "Credit")], max_length=6
                )),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("description", models.CharField(max_length=255)),
                ("operation_ref", models.UUIDField(db_index=True, default=uuid.uuid4)),
                ("balance_after", models.DecimalField(decimal_places=2, max_digits=14)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("created_by_ref", models.UUIDField(blank=True, null=True)),
            ],
            options={
                "db_table": "ledger_entry",
            },
        ),
        migrations.CreateModel(
            name="EscrowHold",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("account", models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="hold",
                    to="escrow.escrowaccount",
                )),
                ("collection_ref", models.CharField(blank=True, max_length=120)),
                ("disbursement_ref", models.CharField(blank=True, max_length=120)),
                ("payment_provider", models.CharField(blank=True, max_length=20)),
                ("gross_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("fee_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("net_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "escrow_hold"},
        ),
        migrations.CreateModel(
            name="FraudGateLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("account", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="fraud_gate_logs",
                    to="escrow.escrowaccount",
                )),
                ("rule_flags", models.JSONField(default=list)),
                ("ml_risk_score", models.DecimalField(blank=True, decimal_places=4, max_digits=5, null=True)),
                ("verdict", models.CharField(max_length=10)),
                ("freeze_reason", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_by_ref", models.UUIDField(blank=True, null=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"db_table": "fraud_gate_log"},
        ),
        migrations.CreateModel(
            name="ReconciliationLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("run_at", models.DateTimeField(auto_now_add=True)),
                ("total_accounts_checked", models.IntegerField(default=0)),
                ("ledger_debit_total", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=18)),
                ("ledger_credit_total", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=18)),
                ("account_balance_total", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=18)),
                ("discrepancy_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=18)),
                ("discrepancy_detected", models.BooleanField(default=False)),
                ("discrepancy_details", models.JSONField(default=list)),
                ("status", models.CharField(default="PASS", max_length=10)),
                ("error_message", models.TextField(blank=True)),
            ],
            options={"db_table": "reconciliation_log"},
        ),
        # Indexes
        migrations.AddIndex(
            model_name="escrowaccount",
            index=models.Index(fields=["state"], name="idx_escrow_account_state"),
        ),
        migrations.AddIndex(
            model_name="escrowaccount",
            index=models.Index(fields=["order_ref"], name="idx_escrow_account_order_ref"),
        ),
        migrations.AddIndex(
            model_name="ledgerentry",
            index=models.Index(fields=["account", "created_at"], name="idx_ledger_account_ts"),
        ),
        migrations.AddIndex(
            model_name="ledgerentry",
            index=models.Index(fields=["entry_type"], name="idx_ledger_entry_type"),
        ),
        migrations.AddIndex(
            model_name="ledgerentry",
            index=models.Index(fields=["operation_ref"], name="idx_ledger_op_ref"),
        ),
        migrations.AddIndex(
            model_name="fraudgatelog",
            index=models.Index(fields=["account", "created_at"], name="idx_fgl_account_ts"),
        ),
    ]
