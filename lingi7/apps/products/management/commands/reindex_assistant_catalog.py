"""
Rebuild the shopping assistant catalog from the Django marketplace.

Exports every visible product (APPROVED status on an APPROVED store) to the
assistant catalog CSV, then pushes the same rows to the live catalog-retriever
``/index/products`` endpoint. Use this after truncating the legacy demo CSV or
whenever the vector catalog must be resynced with the database.

The CSV is overwritten (not appended to), so stale rows left behind by the old
demo seed are removed. The live Milvus index is append-only and deduplicates by
product_id at query time, so run this against a freshly seeded Milvus volume to
fully drop legacy vectors.

Usage:
    python manage.py reindex_assistant_catalog
    python manage.py reindex_assistant_catalog --no-push
    python manage.py reindex_assistant_catalog --batch-size 25
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.products.assistant_index import AssistantCatalogIndexer
from apps.products.models import Product, Store


class Command(BaseCommand):
    help = "Export visible products to the assistant catalog CSV and reindex the retriever."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--no-push",
            action="store_true",
            help="Only rewrite the CSV; do not push to the catalog retriever.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Number of products per request to the catalog retriever.",
        )

    def handle(self, *args, **options) -> None:
        products = list(
            Product.objects.filter(
                status=Product.Status.APPROVED,
                store__status=Store.Status.APPROVED,
            )
            .select_related("category", "store")
            .prefetch_related("images")
            .order_by("pk")
        )

        rows = AssistantCatalogIndexer.export_rows(products)
        AssistantCatalogIndexer.write_csv(rows)
        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {len(rows)} visible product(s) to the assistant catalog CSV."
            )
        )

        if options["no_push"]:
            self.stdout.write("Skipping retriever push (--no-push).")
            return

        if not rows:
            self.stdout.write("No products to push to the retriever.")
            return

        result = AssistantCatalogIndexer.push_many(
            rows, batch_size=max(1, options["batch_size"])
        )
        message = f"Pushed {result['pushed']} product(s) to the retriever."
        if result["failed"]:
            self.stdout.write(self.style.WARNING(f"{message} Failed: {result['failed']}."))
        else:
            self.stdout.write(self.style.SUCCESS(message))
