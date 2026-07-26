"""
apps/admin_audit/migrations/0001_initial.py
============================================
Initial migration for the AdminAuditLog model.

Key design notes:
* UUID primary key — prevents sequential enumeration of audit rows.
* actor is SET_NULL so that deleting an admin user does not cascade-delete
  their audit trail.
* Composite indexes on (actor, timestamp), (target_content_type, target_object_id),
  and (action_type, timestamp) for the most common audit query patterns.
* default_permissions = ("view",) — no add/change/delete in Django admin.
"""

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Create the AdminAuditLog table."""

    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AdminAuditLog",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "actor_email",
                    models.EmailField(
                        db_index=True,
                        help_text="Denormalised actor email — retained even if the user record is deleted.",
                        max_length=254,
                    ),
                ),
                (
                    "action_type",
                    models.CharField(
                        choices=[
                            ("CREATE", "Create"),
                            ("UPDATE", "Update"),
                            ("DELETE", "Delete"),
                            ("SOFT_DELETE", "Soft Delete"),
                            ("RESTORE", "Restore"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                (
                    "target_content_type",
                    models.CharField(
                        db_index=True,
                        help_text='e.g. "users.user", "escrow.escrowaccount"',
                        max_length=200,
                    ),
                ),
                (
                    "target_object_id",
                    models.CharField(
                        db_index=True,
                        help_text="String representation of the target object PK.",
                        max_length=255,
                    ),
                ),
                (
                    "target_repr",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="str() of the target object at the time of action.",
                        max_length=500,
                    ),
                ),
                (
                    "before_state",
                    models.JSONField(
                        blank=True,
                        default=None,
                        help_text="Serialised object state BEFORE the action.  NULL for CREATE.",
                        null=True,
                    ),
                ),
                (
                    "after_state",
                    models.JSONField(
                        blank=True,
                        default=None,
                        help_text="Serialised object state AFTER the action.  NULL for DELETE.",
                        null=True,
                    ),
                ),
                (
                    "ip_address",
                    models.GenericIPAddressField(
                        blank=True,
                        help_text="IPv4 or IPv6 address of the request origin.",
                        null=True,
                    ),
                ),
                (
                    "user_agent",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="HTTP User-Agent header (truncated to 512 chars).",
                        max_length=512,
                    ),
                ),
                (
                    "session_key",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        help_text="Django session key at the time of action.",
                        max_length=64,
                    ),
                ),
                (
                    "timestamp",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        editable=False,
                        help_text="UTC timestamp.  Never update this field.",
                    ),
                ),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        db_index=True,
                        help_text="The admin user who performed the action. NULL if the user has since been deleted.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Admin Audit Log",
                "verbose_name_plural": "Admin Audit Logs",
                "ordering": ["-timestamp"],
                "default_permissions": ("view",),
            },
        ),
        migrations.AddIndex(
            model_name="adminauditlog",
            index=models.Index(
                fields=["actor", "timestamp"],
                name="audit_actor_ts_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="adminauditlog",
            index=models.Index(
                fields=["target_content_type", "target_object_id"],
                name="audit_target_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="adminauditlog",
            index=models.Index(
                fields=["action_type", "timestamp"],
                name="audit_action_ts_idx",
            ),
        ),
    ]
