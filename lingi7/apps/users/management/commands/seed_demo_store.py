"""
Management command to create the demo "LINGI" vendor store with a full
marketplace catalog.

Creates (or upgrades) the test vendor account (Ringson Banda,
+260977872837 / test12345), submits and approves KYC, registers and approves
their store "LINGI", then creates ZMW-priced products across electronics,
men's / women's / children's fashion, and beauty.

Product approval goes through ProductService.approve_product, which fires
AssistantCatalogIndexer.index_product — so each product is also exported to
assistant/shared/data/products_extended.csv and pushed to the live
catalog-retriever /index/products endpoint for AI retrieval.

Idempotent — re-running upgrades the account and repairs any missing
KYC/store/product approval.

Usage:
    python manage.py seed_demo_store
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify

from apps.products.models import Category, InventoryRecord, Product, Store
from apps.products.services import ProductService, StoreService
from apps.users.models import KYCStatus, UserRole
from apps.users.services import UserService

User = get_user_model()

logger = logging.getLogger(__name__)

DEFAULT_NRC = "888888/02/1"
DEFAULT_ADDRESS = "Plot 14, Cairo Road, Lusaka, Zambia"

# Root -> leaf categories created for the demo catalog.
CATEGORY_TREE = {
    "Electronics": [
        "Mobile Phones",
        "Headphones & Earbuds",
        "Phone Accessories",
        "Smartwatches",
    ],
    "Men's Fashion": [
        "Men's Shirts",
        "Men's Trousers",
        "Men's Shoes",
        "Men's Jackets",
    ],
    "Women's Fashion": [
        "Women's Dresses",
        "Women's Skirts",
        "Women's Blouses",
        "Women's Shoes",
    ],
    "Children's Fashion": [
        "Boys' Clothing",
        "Girls' Clothing",
        "Kids' Shoes",
    ],
    "Beauty": [
        "Skincare",
        "Makeup",
        "Hair Care",
        "Fragrance",
    ],
}

# subcategory -> root, derived from CATEGORY_TREE at module import.
SUBCATEGORY_ROOT: dict[str, str] = {}
for _root_name, _children in CATEGORY_TREE.items():
    for _child in _children:
        SUBCATEGORY_ROOT[_child] = _root_name

# (name, price ZMW, subcategory, condition, description, sku)
# Every subcategory referenced here must exist in CATEGORY_TREE.
DEMO_PRODUCTS = [
    # ---- Electronics ----
    (
        "Samsung Galaxy A15 128GB",
        "2450.00",
        "Mobile Phones",
        Product.Condition.NEW,
        (
            "Samsung Galaxy A15 128GB smartphone with a 6.5-inch Super AMOLED "
            "HD+ display, 8GB RAM, 50MP triple rear camera and a 5000mAh "
            "battery. Dual-SIM with 4G LTE and expandable storage up to 1TB — "
            "a dependable everyday phone. Ships from Lusaka, Zambia. "
            "Price: K 2,450.00 (Zambian Kwacha)."
        ),
        "LINGI-SGA15-128",
    ),
    (
        "Tecno Spark 20C 128GB",
        "1799.00",
        "Mobile Phones",
        Product.Condition.NEW,
        (
            "Tecno Spark 20C 128GB smartphone with a 6.6-inch 90Hz punch-hole "
            "display, 8GB RAM, 50MP dual camera and a 5000mAh battery with "
            "18W fast charging. Slim design in glossy green — budget-friendly "
            "and reliable. Ships from Lusaka, Zambia. "
            "Price: K 1,799.00 (Zambian Kwacha)."
        ),
        "LINGI-TNS20C-128",
    ),
    (
        "Apple iPhone 11 64GB (Certified Refurbished)",
        "5200.00",
        "Mobile Phones",
        Product.Condition.REFURBISHED,
        (
            "Apple iPhone 11 64GB in excellent certified-refurbished "
            "condition with a 6.1-inch Liquid Retina display, A13 Bionic chip "
            "and dual 12MP cameras. Includes a 6-month warranty for peace of "
            "mind. Ships from Lusaka, Zambia. "
            "Price: K 5,200.00 (Zambian Kwacha)."
        ),
        "LINGI-APH11-64RB",
    ),
    (
        "JBL Tune 510BT Wireless Headphones",
        "1250.00",
        "Headphones & Earbuds",
        Product.Condition.NEW,
        (
            "JBL Tune 510BT on-ear wireless headphones with JBL Pure Bass "
            "sound, Bluetooth 5.0, 40 hours of playtime and quick-charge "
            "support (5 minutes for 2 hours). Lightweight, foldable and "
            "comfortable for all-day listening. Ships from Lusaka, Zambia. "
            "Price: K 1,250.00 (Zambian Kwacha)."
        ),
        "LINGI-JBL510BT",
    ),
    (
        "Anker PowerCore 20000mAh Power Bank",
        "899.00",
        "Phone Accessories",
        Product.Condition.NEW,
        (
            "Anker PowerCore 20000mAh dual-port power bank with PowerIQ "
            "technology and trickle charging, capable of recharging a phone "
            "several times before needing a top-up. Fits easily in a pocket. "
            "Ships from Lusaka, Zambia. "
            "Price: K 899.00 (Zambian Kwacha)."
        ),
        "LINGI-ANK20K",
    ),
    (
        "Huawei Band 8 Smartwatch Fitness Tracker",
        "750.00",
        "Smartwatches",
        Product.Condition.NEW,
        (
            "Huawei Band 8 slim smartwatch tracker with a 1.47-inch AMOLED "
            "display, heart-rate and SpO2 monitoring, 100+ workout modes and "
            "up to 14 days of battery life. Water-resistant and comfortable "
            "to wear around the clock. Ships from Lusaka, Zambia. "
            "Price: K 750.00 (Zambian Kwacha)."
        ),
        "LINGI-HWB8",
    ),
    # ---- Men's Fashion ----
    (
        "Classic Oxford White Shirt",
        "350.00",
        "Men's Shirts",
        Product.Condition.NEW,
        (
            "Classic Oxford white shirt in soft cotton with a button-down "
            "collar — a timeless addition to any man's wardrobe. Machine "
            "washable, available from XS to XXL. "
            "Price: K 350.00 (Zambian Kwacha)."
        ),
        "LINGI-MNS-OXWHT",
    ),
    (
        "Navy Blue Chino Shirt",
        "320.00",
        "Men's Shirts",
        Product.Condition.NEW,
        (
            "Navy blue chino shirt with a regular fit, crisp collar and "
            "breathable cotton twill fabric. Great for the office or a "
            "casual weekend. "
            "Price: K 320.00 (Zambian Kwacha)."
        ),
        "LINGI-MNS-CHNVO",
    ),
    (
        "Short-Sleeve Linen Shirt",
        "300.00",
        "Men's Shirts",
        Product.Condition.NEW,
        (
            "Lightweight short-sleeve linen shirt in stone beige, ideal for "
            "Lusaka's warm weather. Breathable, relaxed fit with chest "
            "pocket. "
            "Price: K 300.00 (Zambian Kwacha)."
        ),
        "LINGI-MNS-LNSL",
    ),
    (
        "Tailored Slim-Fit Chinos",
        "380.00",
        "Men's Trousers",
        Product.Condition.NEW,
        (
            "Slim-fit chinos in khaki with a tailored waistband and "
            "slight stretch for all-day comfort. Pairs well with a blazer "
            "or a polo. "
            "Price: K 380.00 (Zambian Kwacha)."
        ),
        "LINGI-MNT-CHNOK",
    ),
    (
        "Straight-Cut Denim Jeans",
        "420.00",
        "Men's Trousers",
        Product.Condition.NEW,
        (
            "Straight-cut denim jeans in mid-wash blue with classic "
            "five-pocket styling and durable cotton denim. "
            "Price: K 420.00 (Zambian Kwacha)."
        ),
        "LINGI-MNT-DNM",
    ),
    (
        "Smart Grey Trousers",
        "360.00",
        "Men's Trousers",
        Product.Condition.NEW,
        (
            "Smart grey dress trousers in a slim fit — the go-to pair for "
            "meetings and formal events. Breathable lining and a clean "
            "crease. "
            "Price: K 360.00 (Zambian Kwacha)."
        ),
        "LINGI-MNT-GRY",
    ),
    (
        "Leather Derby Dress Shoes",
        "1150.00",
        "Men's Shoes",
        Product.Condition.NEW,
        (
            "Polished leather Derby dress shoes in black with a durable "
            "sole and cushioned insole for formal occasions. "
            "Price: K 1,150.00 (Zambian Kwacha)."
        ),
        "LINGI-MNSH-DRB",
    ),
    (
        "White Athletic Sneakers",
        "650.00",
        "Men's Shoes",
        Product.Condition.NEW,
        (
            "Clean white athletic sneakers with a cushioned sole and "
            "breathable mesh upper — comfortable for everyday wear and "
            "light training. "
            "Price: K 650.00 (Zambian Kwacha)."
        ),
        "LINGI-MNSH-SNK",
    ),
    (
        "Brown Leather Loafers",
        "780.00",
        "Men's Shoes",
        Product.Condition.NEW,
        (
            "Brown leather loafers with penny-bar detail and a softly "
            "cushioned footbed — slip on for smart-casual looks. "
            "Price: K 780.00 (Zambian Kwacha)."
        ),
        "LINGI-MNSH-LFR",
    ),
    (
        "Men's Bomber Jacket",
        "850.00",
        "Men's Jackets",
        Product.Condition.NEW,
        (
            "Stylish bomber jacket in black with ribbed cuffs and hem, "
            "front zip and two pockets. Lightweight for layering. "
            "Price: K 850.00 (Zambian Kwacha)."
        ),
        "LINGI-MNJ-BMB",
    ),
    (
        "Men's Denim Jacket",
        "700.00",
        "Men's Jackets",
        Product.Condition.NEW,
        (
            "Classic denim jacket in blue with button front and chest "
            "pockets — a durable everyday staple. "
            "Price: K 700.00 (Zambian Kwacha)."
        ),
        "LINGI-MNJ-DNM",
    ),
    (
        "Men's Lightweight Blazer",
        "950.00",
        "Men's Jackets",
        Product.Condition.NEW,
        (
            "Single-breasted lightweight blazer in charcoal with notched "
            "lapels — perfect for smart occasions without the weight of a "
            "full suit. "
            "Price: K 950.00 (Zambian Kwacha)."
        ),
        "LINGI-MNJ-BLZ",
    ),
    # ---- Women's Fashion ----
    (
        "Floral Midi Dress",
        "550.00",
        "Women's Dresses",
        Product.Condition.NEW,
        (
            "Floral midi dress with a flattering cinched waist, short "
            "sleeves and a flowing skirt. Light and airy for daytime or "
            "weddings. "
            "Price: K 550.00 (Zambian Kwacha)."
        ),
        "LINGI-WND-FLR",
    ),
    (
        "Little Black Cocktail Dress",
        "780.00",
        "Women's Dresses",
        Product.Condition.NEW,
        (
            "Elegant little black cocktail dress in stretch crepe with a "
            "knee-length A-line silhouette. "
            "Price: K 780.00 (Zambian Kwacha)."
        ),
        "LINGI-WND-LBD",
    ),
    (
        "Maxi Evening Dress",
        "890.00",
        "Women's Dresses",
        Product.Condition.NEW,
        (
            "Floor-length maxi evening dress in deep emerald with a "
            "halter neck and sweeping skirt for special occasions. "
            "Price: K 890.00 (Zambian Kwacha)."
        ),
        "LINGI-WND-MXI",
    ),
    (
        "Pleated Midi Skirt",
        "320.00",
        "Women's Skirts",
        Product.Condition.NEW,
        (
            "Pleated midi skirt in soft ivory with an elasticated waistband "
            "— feminine and easy to style with any top. "
            "Price: K 320.00 (Zambian Kwacha)."
        ),
        "LINGI-WNSK-PLT",
    ),
    (
        "Denim A-Line Skirt",
        "290.00",
        "Women's Skirts",
        Product.Condition.NEW,
        (
            "Denim A-line skirt in classic blue wash with button front and "
            "rear pockets. "
            "Price: K 290.00 (Zambian Kwacha)."
        ),
        "LINGI-WNSK-DNM",
    ),
    (
        "Pencil Work Skirt",
        "350.00",
        "Women's Skirts",
        Product.Condition.NEW,
        (
            "Tailored pencil skirt in charcoal with a back vent and "
            "stretch waistband for the office. "
            "Price: K 350.00 (Zambian Kwacha)."
        ),
        "LINGI-WNSK-PNC",
    ),
    (
        "Silk Button-Up Blouse",
        "420.00",
        "Women's Blouses",
        Product.Condition.NEW,
        (
            "Silk-touch button-up blouse in blush pink with a relaxed "
            "fit and pearl buttons. "
            "Price: K 420.00 (Zambian Kwacha)."
        ),
        "LINGI-WNB-SLK",
    ),
    (
        "Ruffled Blouse",
        "380.00",
        "Women's Blouses",
        Product.Condition.NEW,
        (
            "Ruffled blouse in white with a V-neck and puff sleeves — a "
            "romantic easy-to-wear staple. "
            "Price: K 380.00 (Zambian Kwacha)."
        ),
        "LINGI-WNB-RFL",
    ),
    (
        "Cotton Poplin Blouse",
        "310.00",
        "Women's Blouses",
        Product.Condition.NEW,
        (
            "Breathable cotton poplin blouse in sky blue with a classic "
            "collar and front button placket. "
            "Price: K 310.00 (Zambian Kwacha)."
        ),
        "LINGI-WNB-PPL",
    ),
    (
        "Black Heeled Sandals",
        "620.00",
        "Women's Shoes",
        Product.Condition.NEW,
        (
            "Black heeled sandals with a 6cm stiletto, ankle strap and "
            "cushioned insole. "
            "Price: K 620.00 (Zambian Kwacha)."
        ),
        "LINGI-WNSH-HLS",
    ),
    (
        "White Ballet Flats",
        "340.00",
        "Women's Shoes",
        Product.Condition.NEW,
        (
            "Comfortable white ballet flats with a soft leather-look "
            "upper and flexible sole. "
            "Price: K 340.00 (Zambian Kwacha)."
        ),
        "LINGI-WNSH-BLF",
    ),
    (
        "Women's Ankle Boots",
        "850.00",
        "Women's Shoes",
        Product.Condition.NEW,
        (
            "Tan ankle boots with a chunky heel, side zip and padded "
            "footbed. "
            "Price: K 850.00 (Zambian Kwacha)."
        ),
        "LINGI-WNSH-BTS",
    ),
    # ---- Children's Fashion ----
    (
        "Boys' Denim Jeans",
        "220.00",
        "Boys' Clothing",
        Product.Condition.NEW,
        (
            "Boys' mid-wash denim jeans with adjustable waist and "
            "reinforced knees, sized 2-12 years. "
            "Price: K 220.00 (Zambian Kwacha)."
        ),
        "LINGI-KBD-DNM",
    ),
    (
        "Boys' Graphic T-Shirt",
        "120.00",
        "Boys' Clothing",
        Product.Condition.NEW,
        (
            "Soft cotton graphic t-shirt in bright blue with a dinosaur "
            "print, pre-shrunk and machine washable. "
            "Price: K 120.00 (Zambian Kwacha)."
        ),
        "LINGI-KBD-TSH",
    ),
    (
        "Boys' Zip-Up Hoodie",
        "260.00",
        "Boys' Clothing",
        Product.Condition.NEW,
        (
            "Zip-up hoodie in grey with a soft brushed lining, kangaroo "
            "pocket and two-tone drawstrings. "
            "Price: K 260.00 (Zambian Kwacha)."
        ),
        "LINGI-KBD-HOD",
    ),
    (
        "Girls' Floral Dress",
        "240.00",
        "Girls' Clothing",
        Product.Condition.NEW,
        (
            "Flutter-sleeve floral dress in soft pink cotton with a "
            "comfortable stretch waistband, sized 2-10 years. "
            "Price: K 240.00 (Zambian Kwacha)."
        ),
        "LINGI-KGD-FLR",
    ),
    (
        "Girls' Skirt and Top Set",
        "210.00",
        "Girls' Clothing",
        Product.Condition.NEW,
        (
            "Two-piece skirt and top set in cheerful yellow with a bow "
            "detail on the waistband. "
            "Price: K 210.00 (Zambian Kwacha)."
        ),
        "LINGI-KGD-ST",
    ),
    (
        "Girls' Button-Up Cardigan",
        "230.00",
        "Girls' Clothing",
        Product.Condition.NEW,
        (
            "Soft knit cardigan in lavender with wooden buttons — easy to "
            "layer over dresses or tees. "
            "Price: K 230.00 (Zambian Kwacha)."
        ),
        "LINGI-KGD-CRD",
    ),
    (
        "Kids' Sports Shoes",
        "320.00",
        "Kids' Shoes",
        Product.Condition.NEW,
        (
            "Lightweight kids' sports shoes with grippy soles, a "
            "double-strap closure and breathable lining, size 8-13. "
            "Price: K 320.00 (Zambian Kwacha)."
        ),
        "LINGI-KSH-SPT",
    ),
    (
        "Kids' School Shoes",
        "300.00",
        "Kids' Shoes",
        Product.Condition.NEW,
        (
            "Durable polishable black school shoes with a wide fit and "
            "non-slip sole, size 9-2. "
            "Price: K 300.00 (Zambian Kwacha)."
        ),
        "LINGI-KSH-SCH",
    ),
    (
        "Kids' Open-Toe Sandals",
        "180.00",
        "Kids' Shoes",
        Product.Condition.NEW,
        (
            "Cushioned open-toe sandals with adjustable straps in brown "
            "— easy for little feet to get on and off. "
            "Price: K 180.00 (Zambian Kwacha)."
        ),
        "LINGI-KSH-SND",
    ),
    # ---- Beauty ----
    (
        "Vitamin C Face Serum",
        "420.00",
        "Skincare",
        Product.Condition.NEW,
        (
            "Brightening vitamin C face serum with hyaluronic acid, "
            "helps even out skin tone and boost radiance. Suitable for "
            "all skin types. "
            "Price: K 420.00 (Zambian Kwacha)."
        ),
        "LINGI-BTY-SRNVITC",
    ),
    (
        "Hyaluronic Acid Moisturiser",
        "380.00",
        "Skincare",
        Product.Condition.NEW,
        (
            "Lightweight hyaluronic acid moisturiser that locks in "
            "hydration all day without feeling greasy. "
            "Price: K 380.00 (Zambian Kwacha)."
        ),
        "LINGI-BTY-SRNHYA",
    ),
    (
        "Gentle Facial Cleanser",
        "260.00",
        "Skincare",
        Product.Condition.NEW,
        (
            "pH-balanced gentle facial cleanser with aloe vera, removes "
            "makeup and impurities without stripping the skin. "
            "Price: K 260.00 (Zambian Kwacha)."
        ),
        "LINGI-BTY-SRNFCS",
    ),
    (
        "Matte Liquid Lipstick",
        "180.00",
        "Makeup",
        Product.Condition.NEW,
        (
            "Long-wearing matte liquid lipstick in classic red, with "
            "high pigmentation and a comfortable non-drying finish. "
            "Price: K 180.00 (Zambian Kwacha)."
        ),
        "LINGI-BTY-MKULST",
    ),
    (
        "Volumising Mascara",
        "200.00",
        "Makeup",
        Product.Condition.NEW,
        (
            "Smudge-proof volumising mascara that adds length and "
            "fullness, easy to remove at the end of the day. "
            "Price: K 200.00 (Zambian Kwacha)."
        ),
        "LINGI-BTY-MKUMSC",
    ),
    (
        "Pressed Powder Foundation",
        "280.00",
        "Makeup",
        Product.Condition.NEW,
        (
            "Pressed powder foundation with SPF that sets makeup and "
            "controls shine, shades from light to deep. "
            "Price: K 280.00 (Zambian Kwacha)."
        ),
        "LINGI-BTY-MKUPDR",
    ),
    (
        "Argan Oil Hair Treatment",
        "250.00",
        "Hair Care",
        Product.Condition.NEW,
        (
            "Pure argan oil hair treatment that tames frizz, adds "
            "shine and nourishes dry ends. "
            "Price: K 250.00 (Zambian Kwacha)."
        ),
        "LINGI-BTY-HCRARG",
    ),
    (
        "Shampoo and Conditioner Set",
        "320.00",
        "Hair Care",
        Product.Condition.NEW,
        (
            "Sulphate-free shampoo and conditioner set with coconut "
            "extract for soft, healthy hair. "
            "Price: K 320.00 (Zambian Kwacha)."
        ),
        "LINGI-BTY-HCRCST",
    ),
    (
        "Coconut Hair Mask",
        "210.00",
        "Hair Care",
        Product.Condition.NEW,
        (
            "Deep-conditioning coconut hair mask, use weekly to repair "
            "damaged and chemically treated hair. "
            "Price: K 210.00 (Zambian Kwacha)."
        ),
        "LINGI-BTY-HCRMSK",
    ),
    (
        "Eau de Parfum 50ml",
        "950.00",
        "Fragrance",
        Product.Condition.NEW,
        (
            "Long-lasting eau de parfum with notes of jasmine, vanilla "
            "and sandalwood in a 50ml bottle. "
            "Price: K 950.00 (Zambian Kwacha)."
        ),
        "LINGI-BTY-FRGEDP",
    ),
    (
        "Men's Musk Cologne 50ml",
        "680.00",
        "Fragrance",
        Product.Condition.NEW,
        (
            "Fresh and woody musk cologne for men, ideal for daily "
            "wear and evenings out. 50ml. "
            "Price: K 680.00 (Zambian Kwacha)."
        ),
        "LINGI-BTY-FRGCOL",
    ),
    (
        "Unisex Citrus Perfume 30ml",
        "520.00",
        "Fragrance",
        Product.Condition.NEW,
        (
            "Bright citrus and bergamot unisex perfume in a travel-sized "
            "30ml spray. "
            "Price: K 520.00 (Zambian Kwacha)."
        ),
        "LINGI-BTY-FRGCIT",
    ),
]


class Command(BaseCommand):
    help = (
        "Create the fully-approved demo LINGI vendor store (Ringson Banda, "
        "+260977872837 / test12345) with a complete ZMW-priced catalog "
        "(electronics, men's / women's / children's fashion, beauty) that is "
        "addable to the cart and retrievable by the shopping assistant."
    )

    def add_arguments(self, parser):
        parser.add_argument("--phone", default="+260977872837")
        parser.add_argument("--password", default="test12345")
        parser.add_argument("--store-name", default="LINGI")
        parser.add_argument("--first-name", default="Ringson")
        parser.add_argument("--last-name", default="Banda")
        parser.add_argument("--admin-phone", default="+260977000001")
        parser.add_argument("--admin-password", default="AdminPass123!")

    def handle(self, *args, **options):
        self._run_tasks_eager()

        phone = options["phone"]
        password = options["password"]
        store_name = options["store_name"]

        admin = self._ensure_admin(options["admin_phone"], options["admin_password"])
        user = self._ensure_vendor(
            phone,
            password,
            options["first_name"],
            options["last_name"],
        )
        self._ensure_kyc_approved(user, admin)
        try:
            store = self._ensure_store_approved(user, store_name, admin)
        except Exception as exc:
            self.stdout.write(self.style.WARNING(
                f"Store/KYC data committed, but a post-commit notification "
                f"failed ({type(exc).__name__}: {exc}). Ignoring — account is live."
            ))
            store = user.store

        categories = self._ensure_categories()
        products = self._ensure_products(store, user, admin, categories)

        self.stdout.write(self.style.SUCCESS(
            f"Demo store ready: {phone} (password: {password}) | "
            f"KYC={user.kyc_status} | store='{store.name}' ({store.status}) | "
            f"products approved: {len(products)}"
        ))
        for product in products:
            self.stdout.write(
                f"  - {product.name} | K {product.price:,.2f} | {product.status}"
            )

    @staticmethod
    def _run_tasks_eager() -> None:
        """Execute Celery notification tasks inline so no broker is required."""
        try:
            from celery import current_app

            current_app.conf.task_always_eager = True
            current_app.conf.task_eager_propagates = False
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not force Celery eager mode: %s", exc)

    def _ensure_admin(self, phone: str, password: str) -> User:
        admin = User.objects.filter(is_superuser=True).order_by("id").first()
        if admin is not None:
            self.stdout.write(f"  Using superuser: {admin.phone_number}")
            return admin

        admin, created = User.objects.get_or_create(
            phone_number=phone,
            defaults={
                "first_name": "Admin",
                "last_name": "Super",
                "role": UserRole.ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "consent_given_at": timezone.now(),
                "phone_verified": True,
                "kyc_status": KYCStatus.VERIFIED,
            },
        )
        if created:
            admin.set_password(password)
            admin.save(update_fields=["password"])
            self.stdout.write(f"  Admin created: {phone}")
        return admin

    def _ensure_vendor(self, phone: str, password: str, first: str, last: str) -> User:
        user, created = User.objects.get_or_create(
            phone_number=phone,
            defaults={
                "first_name": first,
                "last_name": last,
                "role": UserRole.VENDOR,
                "is_active": True,
                "phone_verified": True,
                "consent_given_at": timezone.now(),
            },
        )
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
            self.stdout.write(f"  Vendor created: {phone}")
        else:
            user.role = UserRole.VENDOR
            user.is_active = True
            user.phone_verified = True
            user.set_password(password)
            user.save(update_fields=["role", "is_active", "phone_verified", "password"])
            self.stdout.write(f"  Vendor upgraded: {phone}")
        return user

    def _ensure_kyc_approved(self, user: User, admin: User) -> None:
        if user.kyc_status == KYCStatus.VERIFIED:
            self.stdout.write("  KYC already VERIFIED")
            return

        users = UserService()
        if user.kyc_status in (KYCStatus.UNVERIFIED, KYCStatus.REJECTED):
            uid = str(user.id)
            users.kyc_submit(
                user_id=uid,
                nrc_number=user.nrc_number or DEFAULT_NRC,
                physical_address=user.physical_address or DEFAULT_ADDRESS,
                province=user.province or "Lusaka",
                nrc_front_key=f"kyc/{uid}/front.jpg",
                nrc_back_key=f"kyc/{uid}/back.jpg",
                selfie_key=f"kyc/{uid}/selfie.jpg",
            )
            self.stdout.write("  KYC submitted -> PENDING")

        users.kyc_approve(user_id=str(user.id), reviewed_by=admin)
        self.stdout.write("  KYC approved -> VERIFIED")

    def _ensure_store_approved(self, user: User, store_name: str, admin: User) -> Store:
        if hasattr(user, "store"):
            store = user.store
            self.stdout.write(f"  Store already exists: {store.name} ({store.status})")
        else:
            conflict = Store.objects.filter(name__iexact=store_name).first()
            if conflict and conflict.owner_id != user.id:
                self.stdout.write(self.style.ERROR(
                    f"Store name '{store_name}' is taken by another owner — aborting."
                ))
                raise SystemExit(1)

            store = StoreService.register_store(
                user,
                {
                    "name": store_name,
                    "description": f"{store_name} store on Lingi7.",
                    "business_type": Store.BusinessType.INDIVIDUAL,
                    "nrc_or_reg_no": user.nrc_number or DEFAULT_NRC,
                    "business_address": user.physical_address or DEFAULT_ADDRESS,
                    "phone_number": user.phone_number,
                },
            )
            self.stdout.write(f"  Store registered: {store.name} ({store.status})")

        if store.status != Store.Status.APPROVED:
            StoreService.approve_store(store, admin)
            self.stdout.write(f"  Store approved: {store.name}")
        else:
            self.stdout.write(f"  Store already APPROVED: {store.name}")
        return store

    def _ensure_categories(self) -> dict[str, Category]:
        categories: dict[str, Category] = {}
        for root_name, children in CATEGORY_TREE.items():
            root, _ = Category.objects.get_or_create(
                slug=slugify(root_name),
                defaults={
                    "name": root_name,
                    "description": f"{root_name} category.",
                    "is_active": True,
                },
            )
            for child_name in children:
                child, _ = Category.objects.get_or_create(
                    slug=slugify(child_name),
                    defaults={
                        "name": child_name,
                        "parent": root,
                        "description": f"{child_name} — {root_name}.",
                        "is_active": True,
                    },
                )
                categories[child_name] = child
        self.stdout.write(
            f"  Categories ready ({len(categories)}): {', '.join(sorted(categories))}"
        )
        return categories

    def _ensure_products(
        self,
        store: Store,
        vendor: User,
        admin: User,
        categories: dict[str, Category],
    ) -> list[Product]:
        results: list[Product] = []
        for name, price, subcategory, condition, description, sku in DEMO_PRODUCTS:
            slug = f"demo-lingi-{slugify(name)}"
            category = categories[subcategory]
            root_name = SUBCATEGORY_ROOT[subcategory]

            product, created = Product.objects.get_or_create(
                store=store,
                slug=slug,
                defaults={
                    "name": name,
                    "category": category,
                    "description": description,
                    "price": Decimal(price),
                    "condition": condition,
                    "sku": sku,
                    "ships_from": "Lusaka",
                    "weight_kg": Decimal("0.500"),
                    "suggested_tags": [root_name, subcategory],
                    "descriptions_i18n": {"en": description},
                    "status": Product.Status.DRAFT,
                },
            )
            if not created:
                needs_reindex = False
                if product.category_id != category.pk:
                    product.category = category
                    needs_reindex = True
                if str(product.price) != price:
                    product.price = Decimal(price)
                    needs_reindex = True
                if needs_reindex:
                    product.save(update_fields=["category", "price", "updated_at"])
                    self.stdout.write(f"  Refreshed metadata: {name}")

            if product.status == Product.Status.ARCHIVED:
                ProductService._transition(
                    product, Product.Status.DRAFT, actor=vendor
                )

            if product.status in (Product.Status.DRAFT, Product.Status.REJECTED):
                try:
                    ProductService.submit_for_review(product, vendor)
                except Exception as exc:
                    self.stdout.write(self.style.WARNING(
                        f"  Could not submit '{name}' ({type(exc).__name__}: {exc})"
                    ))

            if product.status == Product.Status.PENDING:
                try:
                    ProductService.approve_product(product, admin)
                    self.stdout.write(f"  Approved + indexed: {name}")
                except Exception as exc:
                    self.stdout.write(self.style.WARNING(
                        f"  Could not approve '{name}' ({type(exc).__name__}: {exc})"
                    ))
            elif product.status == Product.Status.APPROVED:
                self.stdout.write(f"  Already APPROVED: {name}")

            self._ensure_inventory(product, quantity=25)
            results.append(product)
        return results

    @staticmethod
    def _ensure_inventory(product: Product, quantity: int) -> None:
        record, created = InventoryRecord.objects.get_or_create(
            product=product,
            defaults={
                "quantity_available": quantity,
                "track_inventory": True,
                "allow_backorder": False,
            },
        )
        if created:
            return
        if record.track_inventory and record.quantity_available < 1:
            record.quantity_available += quantity
            record.save(update_fields=["quantity_available", "updated_at"])