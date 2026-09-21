"""
apps/escrow/migrations/0005_escrow_ledger_schema_repair.py

Repairs migration drift: escrow tables were originally created in the
'public' schema (0001_initial used a plain db_table name) while the models
now reference schema-qualified names (Meta.db_table = "escrow_ledger"."...").

Django does not track db_table changes in migrations, so tables that exist
in 'public' are re-aligned into the escrow_ledger schema on upgrades. The
statements are guarded with IF EXISTS so they are also safe on fresh installs
where the tables were already created in the correct schema.
"""
from __future__ import annotations

from django.db import migrations

TABLE_NAMES = [
    "escrow_account",
    "ledger_entry",
    "escrow_hold",
    "fraud_gate_log",
    "reconciliation_log",
]


def _move_tables(apps, schema_editor, to_schema: str) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    quote = schema_editor.quote_name
    for table in TABLE_NAMES:
        schema_editor.execute(
            f"ALTER TABLE IF EXISTS public.{quote(table)} SET SCHEMA {quote(to_schema)}"
        )


def move_into_escrow_ledger(apps, schema_editor) -> None:
    _move_tables(apps, schema_editor, "escrow_ledger")


def move_back_to_public(apps, schema_editor) -> None:
    _move_tables(apps, schema_editor, "public")


class Migration(migrations.Migration):

    dependencies = [
        ("escrow", "0004_alter_escrowaccount_state"),
    ]

    operations = [
        migrations.RunPython(move_into_escrow_ledger, move_back_to_public),
    ]