"""
apps/escrow/migrations/0006_add_optimistic_lock_fields.py

Adds the optimistic-concurrency columns that drifted from the models:

  * EscrowAccount.version      — incremented on every balance/state mutation
  * LedgerEntry.account_version — sequence number of the account at write time

These fields were added to the models after 0001_initial but no migration was
ever generated, so production databases (and fresh installs) were missing
the columns. On PostgreSQL the escrow tables already sit in the escrow_ledger
schema (see 0005_escrow_ledger_schema_repair), so the additions are scoped to
the schema-qualified table names.
"""
from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("escrow", "0005_escrow_ledger_schema_repair"),
    ]

    operations = [
        migrations.AddField(
            model_name="escrowaccount",
            name="version",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="ledgerentry",
            name="account_version",
            field=models.PositiveIntegerField(default=0),
        ),
    ]