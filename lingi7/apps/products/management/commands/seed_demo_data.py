"""
Management command to seed demo data for the Lingi7 e-commerce store.

Creates categories, a demo vendor user, an approved store, and sample
products with images from assistant/shared/images/.

Usage:
    python manage.py seed_demo_data
    python manage.py seed_demo_data --image-dir /path/to/images
    python manage.py seed_demo_data --products 20
"""

from __future__ import annotations

import os
import io
import random
from pathlib import Path
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.contrib.auth import get_user_model
from PIL import Image, ImageDraw, ImageFont

from apps.products.models import Category, Store, Product
from apps.products.services import StoreService, ProductService

User = get_user_model()

# ---------------------------------------------------------------------------
# Seed data — categories
# ---------------------------------------------------------------------------

CATEGORIES: list[dict] = [
    {
        "name": "Electronics",
        "children": [
            {"name": "Mobile Phones", "children": ["Smartphones", "Feature Phones"]},
            {"name": "Laptops & Computers", "children": ["Laptops", "Tablets", "Desktop Accessories"]},
            {"name": "Audio", "children": ["Headphones", "Speakers", "Earbuds"]},
        ],
    },
    {
        "name": "Fashion",
        "children": [
            {"name": "Women's Clothing", "children": ["Dresses", "Tops", "Skirts", "Outerwear"]},
            {"name": "Men's Clothing", "children": ["Shirts", "Trousers", "Jackets"]},
            {"name": "Accessories", "children": ["Bags", "Sunglasses", "Jewelry", "Shoes"]},
        ],
    },
    {
        "name": "Home & Garden",
        "children": [
            {"name": "Furniture", "children": ["Sofas", "Tables", "Chairs"]},
            {"name": "Kitchen", "children": ["Cookware", "Utensils", "Appliances"]},
            {"name": "Decor", "children": ["Lighting", "Wall Art", "Cushions"]},
        ],
    },
]

# ---------------------------------------------------------------------------
# Sample product definitions — each maps to a matching image filename
# ---------------------------------------------------------------------------

SAMPLE_PRODUCTS: list[dict] = [
    {"name": "Aesthetic A-Line Skirt in Soft Linen", "category": "Skirts", "price": "89.00", "image_match": "Aesthetic_A-Line_Skirt_in_Soft_Linen"},
    {"name": "Alegria Ballet Flat in Navy", "category": "Shoes", "price": "120.00", "image_match": "Alegria_Ballet_Flat_in_Navy"},
    {"name": "Aria Aviator Sunglasses", "category": "Sunglasses", "price": "65.00", "image_match": "Aria_Aviator_Sunglasses"},
    {"name": "Aria Leather Crossbody Bag", "category": "Bags", "price": "145.00", "image_match": "Aria_Leather_Crossbody_Bag"},
    {"name": "Asian Print Tote Bag", "category": "Bags", "price": "78.00", "image_match": "Asian_Print_Tote_Bag"},
    {"name": "Avelina Satin Sheath Dress", "category": "Dresses", "price": "159.00", "image_match": "Avelina_Satin_Sheath_Dress"},
    {"name": "Beaded Bracelet Set", "category": "Jewelry", "price": "34.00", "image_match": "Beaded_Bracelet_Set"},
    {"name": "Bella Breeze Hoops", "category": "Jewelry", "price": "28.00", "image_match": "Bella_Breeze_Hoops"},
    {"name": "Belleza Ballet Heels in Silver", "category": "Shoes", "price": "135.00", "image_match": "Belleza_Ballet_Heels_in_Silver"},
    {"name": "Black Satin Lace-Up Dress", "category": "Dresses", "price": "189.00", "image_match": "Black_Satin_Lace-Up_Dress"},
    {"name": "Black Velvet Ankle Boots", "category": "Shoes", "price": "165.00", "image_match": "Black_Velvet_Ankle_Boots"},
    {"name": "Canvas Tote Bag", "category": "Bags", "price": "55.00", "image_match": "Chic_Canvas_Tote_Bag"},
    {"name": "Chic Cat-Eye Sunglasses", "category": "Sunglasses", "price": "72.00", "image_match": "Chic_Cat-Eye_Sunglasses"},
    {"name": "Classic Cognac Heels", "category": "Shoes", "price": "148.00", "image_match": "Classic_Cognac_Heels"},
    {"name": "Coral Silk Maxi Dress", "category": "Dresses", "price": "199.00", "image_match": "Coral_Silk_Maxi_Dress"},
    {"name": "Delicate Lace Blouse Sweater", "category": "Tops", "price": "82.00", "image_match": "Delicate_Lace_Blouse_Sweater"},
    {"name": "Elegant Embroidered Crossbody Bag", "category": "Bags", "price": "110.00", "image_match": "Elegant_Embroidered_Crossbody_Bag"},
    {"name": "Floral Print Maxi Skirt", "category": "Skirts", "price": "92.00", "image_match": "Floral_Print_Maxi_Skirt"},
    {"name": "Gardenia Silk Maxi Dress", "category": "Dresses", "price": "220.00", "image_match": "Gardenia_Silk_Maxi_Dress"},
    {"name": "Gold Hoop Earrings", "category": "Jewelry", "price": "45.00", "image_match": "Havana_Gold_Earrings"},
    {"name": "Intricate Lace Gown", "category": "Dresses", "price": "275.00", "image_match": "Intricate_Lace_Gown"},
    {"name": "Jade Suede Heels", "category": "Shoes", "price": "155.00", "image_match": "Jade_Suede_Heels"},
    {"name": "Jasmine Silk Skirt", "category": "Skirts", "price": "98.00", "image_match": "Jasmine_Silk_Skirt"},
    {"name": "Kaleidoscope Crossbody Bag", "category": "Bags", "price": "105.00", "image_match": "Kaleidoscope_Crossbody_Bag"},
    {"name": "Lace and Silk Blouse", "category": "Tops", "price": "76.00", "image_match": "Lace_and_Silk_Blouse"},
    {"name": "Navy Velvet Maxi Dress", "category": "Dresses", "price": "185.00", "image_match": "Navy_Velvet_Maxi_Dress"},
    {"name": "Opulent Leather Tote Bag", "category": "Bags", "price": "195.00", "image_match": "Opulent_Leather_Tote_Bag"},
    {"name": "Pearl Bracelet", "category": "Jewelry", "price": "39.00", "image_match": "Pearl_Bracelet"},
    {"name": "Rose Petal Maxi Dress", "category": "Dresses", "price": "169.00", "image_match": "Rose_Petal_Maxi_Dress"},
    {"name": "Sleek Leather Satchel Bag", "category": "Bags", "price": "160.00", "image_match": "Sleek_Leather_Satchel_Bag"},
    {"name": "Vivacious Velvet Dress", "category": "Dresses", "price": "210.00", "image_match": "Vivacious_Velvet_Dress"},
    {"name": "Woven Floral Maxi Dress", "category": "Dresses", "price": "178.00", "image_match": "Woven_Floral_Maxi_Dress"},
    {"name": "Acetate Oval Sunglasses in Red", "category": "Sunglasses", "price": "58.00", "image_match": "Acetate_Oval_Sunglasses_in_Red"},
    {"name": "Charming Cognac Heels", "category": "Shoes", "price": "142.00", "image_match": "Charming_Cognac_Heels"},
    {"name": "Radiant Rose Silk Maxi Dress", "category": "Dresses", "price": "230.00", "image_match": "Radiant_Rose_Silk_Maxi_Dress"},
    {"name": "Vivienne Lace Dress", "category": "Dresses", "price": "195.00", "image_match": "Vivienne_Lace_Dress"},
    {"name": "Zephyr Linen Skirt", "category": "Skirts", "price": "85.00", "image_match": "Zephyr_Linen_Skirt"},
    {"name": "Solo Pearl Necklace", "category": "Jewelry", "price": "52.00", "image_match": "Solo_Pearl_Necklace"},
    {"name": "Trendy Turtleneck Sweater", "category": "Tops", "price": "68.00", "image_match": "Trendy_Turtleneck_Sweater"},
    {"name": "Soft Ballet Flats in Blush Pink", "category": "Shoes", "price": "95.00", "image_match": "Soft_Ballet_Flats_in_Blush_Pink_Leather"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_placeholder_image(name: str) -> ContentFile:
    img = Image.new("RGB", (600, 600), color=(random.randint(30, 220), random.randint(30, 220), random.randint(30, 220)))
    draw = ImageDraw.Draw(img)
    draw.text((30, 280), name[:40], fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75)
    return ContentFile(buf.getvalue(), name="placeholder.jpg")


def _load_image(image_dir: Path, product_name: str, image_match: str) -> ContentFile | None:
    for ext in (".jpg", ".jpeg", ".png"):
        candidates = list(image_dir.glob(f"{image_match}*{ext}")) + list(image_dir.glob(f"{image_match}*{ext.upper()}"))
        for path in candidates:
            if path.is_file():
                data = path.read_bytes()
                filename = f"{image_match}{ext}"
                return ContentFile(data, name=filename)
    return None


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Seed the database with demo categories, store, and products."

    def add_arguments(self, parser):
        parser.add_argument(
            "--image-dir",
            default=None,
            help="Path to directory containing sample product images. "
                 "Defaults to ../assistant/shared/images/ relative to project root.",
        )
        parser.add_argument(
            "--products",
            type=int,
            default=15,
            help="Number of sample products to create (max 40). Default: 15.",
        )
        parser.add_argument(
            "--vendor-phone",
            default="+260971234568",
            help="Phone number for the demo vendor. Default: +260971234568.",
        )
        parser.add_argument(
            "--vendor-password",
            default="DemoPass123!",
            help="Password for the demo vendor. Default: DemoPass123!.",
        )
        parser.add_argument(
            "--skip-if-exists",
            action="store_true",
            default=True,
            help="Skip seeding if products already exist. Default: True.",
        )

    def handle(self, *args, **options):
        count = min(options["products"], 40)
        vendor_phone = options["vendor_phone"]
        vendor_password = options["vendor_password"]
        skip_if_exists = options["skip_if_exists"]
        image_dir = options["image_dir"]

        # Determine image directory
        if image_dir:
            img_path = Path(image_dir)
        else:
            project_root = Path(os.getcwd())
            img_path = project_root.parent / "assistant" / "shared" / "images"

        self.stdout.write(f"Image directory: {img_path}")
        if img_path.is_dir():
            self.stdout.write(f"Found {len(list(img_path.glob('*')))} files")
        else:
            self.stdout.write(self.style.WARNING("Image directory not found — will generate placeholder images"))

        if skip_if_exists and Product.objects.exists():
            self.stdout.write(self.style.WARNING("Products already exist. Skipping seed (use --skip-if-exists=0 to force)."))
            return

        with transaction.atomic():
            self._seed_categories()
            vendor = self._seed_vendor(vendor_phone, vendor_password)
            store = self._seed_store(vendor)
            self._seed_products(store, count, img_path)

        self.stdout.write(self.style.SUCCESS(f"Seed complete: {count} products in store '{store.name}'"))

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------

    def _seed_categories(self):
        created = 0
        for root_cat in CATEGORIES:
            root, _ = Category.objects.get_or_create(
                name=root_cat["name"],
                defaults={"slug": root_cat["name"].lower().replace(" & ", "-").replace(" ", "-")},
            )
            created += 1
            for sub_cat in root_cat.get("children", []):
                sub, _ = Category.objects.get_or_create(
                    name=sub_cat["name"],
                    parent=root,
                    defaults={
                        "slug": f"{root.slug}-{sub_cat['name'].lower().replace(' ', '-')}",
                    },
                )
                created += 1
                for leaf_name in sub_cat.get("children", []):
                    Category.objects.get_or_create(
                        name=leaf_name,
                        parent=sub,
                        defaults={
                            "slug": f"{sub.slug}-{leaf_name.lower().replace(' ', '-')}",
                        },
                    )
                    created += 1
        self.stdout.write(f"  Categories: {created} created")

    # ------------------------------------------------------------------
    # Vendor user
    # ------------------------------------------------------------------

    def _seed_vendor(self, phone: str, password: str) -> User:
        user, created = User.objects.get_or_create(
            phone_number=phone,
            defaults={
                "first_name": "Demo",
                "last_name": "Vendor",
                "role": "VENDOR",
                "is_active": True,
                "nrc_number": "123456/78/1",
                "physical_address": "123 Cairo Road, Lusaka, Zambia",
                "province": "Lusaka",
            },
        )
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
            self.stdout.write(f"  Vendor created: {phone}")
        else:
            self.stdout.write(f"  Vendor already exists: {phone}")
        return user

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    def _seed_store(self, vendor: User) -> Store:
        store, created = Store.objects.get_or_create(
            owner=vendor,
            defaults={
                "name": "Demo Store Zambia",
                "status": Store.Status.PENDING,
                "business_type": Store.BusinessType.INDIVIDUAL,
                "nrc_or_reg_no": vendor.nrc_number or "123456/78/1",
                "business_address": vendor.physical_address or "123 Cairo Road, Lusaka",
                "phone_number": vendor.phone_number,
                "description": "Your premier demo store showcasing the Lingi7 e-commerce platform.",
            },
        )
        if created:
            self.stdout.write(f"  Store created: {store.name}")
            StoreService.approve_store(store, vendor)
            self.stdout.write(f"  Store approved: {store.name}")
        else:
            self.stdout.write(f"  Store already exists: {store.name}")
            if store.status != Store.Status.APPROVED:
                StoreService.approve_store(store, vendor)
                self.stdout.write(f"  Store approved: {store.name}")
        return store

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    def _seed_products(self, store: Store, count: int, img_dir: Path):
        category_map: dict[str, Category] = {}
        for cat in Category.objects.all():
            category_map[cat.name] = cat

        products_to_create = SAMPLE_PRODUCTS[:count]
        created_count = 0

        for idx, prod_def in enumerate(products_to_create):
            category = category_map.get(prod_def["category"])
            if not category:
                self.stdout.write(self.style.WARNING(f"  Category '{prod_def['category']}' not found — skipping"))
                continue

            slug_base = prod_def["name"].lower().replace(" ", "-").replace("'", "").replace("&", "and")
            product = ProductService.create_product(store, {
                "category": category,
                "name": prod_def["name"],
                "slug": f"{slug_base}-{idx}",
                "description": f"High-quality {prod_def['name'].lower()} — available now at Demo Store Zambia.",
                "price": Decimal(prod_def["price"]),
                "sku": f"DEMO-{idx+1:04d}",
                "initial_quantity": random.randint(10, 100),
                "track_inventory": True,
            })

            # Attach image
            image_file = None
            if img_dir.is_dir():
                image_file = _load_image(img_dir, prod_def["name"], prod_def["image_match"])
            if not image_file:
                image_file = _make_placeholder_image(prod_def["name"])

            ProductService.add_image(product, image_file, alt_text=prod_def["name"])

            # Submit & approve
            ProductService.submit_for_review(product, store.owner)
            ProductService.approve_product(product, store.owner)

            created_count += 1
            self.stdout.write(f"  [{created_count}/{count}] {prod_def['name']} — K{prod_def['price']}")

        if created_count < count:
            remaining = count - created_count
            self.stdout.write(f"  Adding {remaining} additional products with placeholder images...")
            for i in range(created_count, count):
                name = f"Demo Product {i+1}"
                slug_base = f"demo-product-{i+1}"
                category = random.choice(list(category_map.values())) if category_map else None
                if not category:
                    break
                product = ProductService.create_product(store, {
                    "category": category,
                    "name": name,
                    "slug": f"{slug_base}-{i}",
                    "description": f"Sample product #{i+1} for demonstration purposes.",
                    "price": Decimal(str(random.randrange(20, 500))),
                    "sku": f"DEMO-{i+1:04d}",
                    "initial_quantity": random.randint(10, 100),
                    "track_inventory": True,
                })
                image_file = _make_placeholder_image(name)
                ProductService.add_image(product, image_file, alt_text=name)
                ProductService.submit_for_review(product, store.owner)
                ProductService.approve_product(product, store.owner)
                created_count += 1
                self.stdout.write(f"  [{created_count}/{count}] {name}")

        self.stdout.write(f"  Products created & approved: {created_count}")
