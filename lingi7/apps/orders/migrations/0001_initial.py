# Generated migration for apps/orders — LG7-BE-006

import uuid
import decimal
import django.db.models.deletion
import django.utils.timezone
import apps.orders.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("escrow", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Order",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reference", models.CharField(db_index=True, default=apps.orders.models._order_ref, max_length=24, unique=True)),
                ("subtotal", models.DecimalField(decimal_places=2, default=decimal.Decimal("0.00"), max_digits=14)),
                ("platform_fee", models.DecimalField(decimal_places=2, default=decimal.Decimal("0.00"), max_digits=14)),
                ("total_amount", models.DecimalField(decimal_places=2, default=decimal.Decimal("0.00"), max_digits=14)),
                ("currency", models.CharField(default="ZMW", max_length=3)),
                ("status", models.CharField(
                    choices=[
                        ("DRAFT", "Draft"), ("PENDING_PAYMENT", "Pending Payment"),
                        ("PAYMENT_RECEIVED", "Payment Received"), ("PROCESSING", "Processing"),
                        ("SHIPPED", "Shipped"), ("DELIVERED", "Delivered"),
                        ("COMPLETED", "Completed"), ("DISPUTED", "Disputed"),
                        ("CANCELLED", "Cancelled"), ("REFUNDED", "Refunded"),
                    ],
                    db_index=True, default="DRAFT", max_length=20
                )),
                ("fulfilment_type", models.CharField(
                    choices=[
                        ("STANDARD_DELIVERY", "Standard Delivery"),
                        ("PICKUP", "Pickup"),
                        ("DIGITAL", "Digital"),
                    ],
                    default="STANDARD_DELIVERY", max_length=20
                )),
                ("delivery_address", models.TextField(blank=True, default="")),
                ("buyer_notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("buyer", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="orders_as_buyer",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("seller", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="orders_as_seller",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("escrow_account", models.OneToOneField(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="order",
                    to="escrow.escrowaccount",
                )),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(fields=["buyer", "status"], name="orders_order_buyer_status_idx"),
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(fields=["seller", "status"], name="orders_order_seller_status_idx"),
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(fields=["status", "created_at"], name="orders_order_status_created_idx"),
        ),
        migrations.CreateModel(
            name="OrderLine",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("product_id", models.CharField(blank=True, default="", max_length=100)),
                ("product_name", models.CharField(max_length=255)),
                ("product_sku", models.CharField(blank=True, default="", max_length=100)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=14,
                    validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.01"))]
                )),
                ("quantity", models.PositiveIntegerField(default=1)),
                ("currency", models.CharField(default="ZMW", max_length=3)),
                ("order", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="lines", to="orders.order",
                )),
            ],
            options={"ordering": ["product_name"]},
        ),
        migrations.CreateModel(
            name="OrderEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("from_status", models.CharField(max_length=20)),
                ("to_status", models.CharField(max_length=20)),
                ("note", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("order", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="events", to="orders.order",
                )),
                ("triggered_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="order_events_triggered",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.CreateModel(
            name="OrderShipment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("carrier", models.CharField(max_length=100)),
                ("tracking_number", models.CharField(blank=True, default="", max_length=200)),
                ("tracking_url", models.URLField(blank=True, default="")),
                ("estimated_delivery", models.DateField(blank=True, null=True)),
                ("shipped_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("order", models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="shipment", to="orders.order",
                )),
            ],
        ),
        migrations.CreateModel(
            name="OrderDispute",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reason", models.CharField(max_length=30)),
                ("description", models.TextField()),
                ("evidence_urls", models.JSONField(blank=True, default=list)),
                ("resolution", models.CharField(blank=True, default="", max_length=20)),
                ("resolution_notes", models.TextField(blank=True, default="")),
                ("refund_amount", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("order", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="disputes", to="orders.order",
                )),
                ("raised_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="disputes_raised", to=settings.AUTH_USER_MODEL,
                )),
                ("resolved_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="disputes_resolved", to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
