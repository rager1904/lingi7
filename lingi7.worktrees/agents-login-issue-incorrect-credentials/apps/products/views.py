"""
apps/products/views.py
======================
Thin ViewSets — all business logic delegated to service classes.

ViewSet groups:
    Public (no auth required):
        CategoryViewSet     — browse category tree
        PublicProductViewSet — browse approved products, detail, search

    Vendor (JWT auth + APPROVED store):
        VendorStoreViewSet      — register, view, update own store
        VendorProductViewSet    — manage own product listings
        VendorDashboardView     — store KPI snapshot
        VendorOrderFulfilmentViewSet — (stub, wired in apps/orders)

    Admin (staff only):
        AdminStoreViewSet   — review and approve/reject/suspend stores
        AdminProductViewSet — review and approve/reject listings
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum
from django.db.models.functions import Coalesce
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.products.exceptions import (
    InvalidProductTransitionError,
    InvalidStoreTransitionError,
    StoreError,
)
from apps.products.models import Category, Product, ProductImage, Store
from apps.products.permissions import IsAdminOrReadOnly, IsStoreApproved, IsStoreOwner, IsVendor
from apps.products.serializers import (
    AdminProductSerializer,
    AdminStoreSerializer,
    CategorySerializer,
    CategoryTreeSerializer,
    ProductImageUploadSerializer,
    PublicProductDetailSerializer,
    PublicProductListSerializer,
    StoreDashboardSerializer,
    StoreDetailSerializer,
    StoreRegistrationSerializer,
    VendorProductSerializer,
)
from apps.products.services import ProductService, StoreService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public — Categories
# ---------------------------------------------------------------------------

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Public read-only category browsing."""

    permission_classes = [AllowAny]
    queryset = Category.objects.filter(is_active=True, parent__isnull=True)
    lookup_field = "slug"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return CategoryTreeSerializer
        return CategorySerializer


# ---------------------------------------------------------------------------
# Public — Products
# ---------------------------------------------------------------------------

class PublicProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Public product catalogue — only APPROVED products in APPROVED stores.

    Supports:
        GET /api/products/           — list with filtering
        GET /api/products/{slug}/    — detail
    Query params: category, min_price, max_price, condition, q (name search)
    """

    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        qs = (
            Product.objects.filter(
                status=Product.Status.APPROVED,
                store__status=Store.Status.APPROVED,
            )
            .select_related("store", "category")
            .prefetch_related("images")
        )

        params = self.request.query_params
        if category := params.get("category"):
            qs = qs.filter(category__slug=category)
        if min_price := params.get("min_price"):
            qs = qs.filter(price__gte=min_price)
        if max_price := params.get("max_price"):
            qs = qs.filter(price__lte=max_price)
        if condition := params.get("condition"):
            qs = qs.filter(condition=condition)
        if q := params.get("q"):
            qs = qs.filter(
                Q(name__icontains=q) | Q(description__icontains=q)
            )
        return qs

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PublicProductDetailSerializer
        return PublicProductListSerializer


# ---------------------------------------------------------------------------
# Vendor — Store registration & management
# ---------------------------------------------------------------------------

class VendorStoreViewSet(viewsets.GenericViewSet):
    """
    Vendor's own store management.

    POST /api/vendor/store/register/ — create store
    GET  /api/vendor/store/          — view own store
    PATCH /api/vendor/store/         — update store profile
    """

    permission_classes = [IsAuthenticated, IsVendor]

    def get_serializer_class(self):
        if self.action == "register":
            return StoreRegistrationSerializer
        return StoreDetailSerializer

    @action(detail=False, methods=["post"], url_path="register")
    def register(self, request: Request) -> Response:
        """Submit a new store registration."""
        serializer = StoreRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            store = StoreService.register_store(
                owner=request.user,
                validated_data=serializer.validated_data,
            )
        except StoreError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            StoreDetailSerializer(store).data, status=status.HTTP_201_CREATED
        )

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request: Request) -> Response:
        """Retrieve the authenticated vendor's store."""
        try:
            store = request.user.store
        except Store.DoesNotExist:
            return Response(
                {"detail": "No store registered for this account."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(StoreDetailSerializer(store).data)

    @action(detail=False, methods=["patch"], url_path="update")
    def update_store(self, request: Request) -> Response:
        """Update mutable store profile fields (name, description, payout info)."""
        try:
            store = request.user.store
        except Store.DoesNotExist:
            return Response(
                {"detail": "No store found."}, status=status.HTTP_404_NOT_FOUND
            )
        serializer = StoreDetailSerializer(store, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Vendor — Products
# ---------------------------------------------------------------------------

class VendorProductViewSet(viewsets.ModelViewSet):
    """
    Vendor product management — scoped to the authenticated vendor's store.

    CRITICAL: get_queryset() always filters by store=request.user.store.
    A vendor CANNOT see or modify another vendor's products.
    """

    permission_classes = [IsAuthenticated, IsVendor, IsStoreApproved]
    serializer_class = VendorProductSerializer

    def get_queryset(self):
        return (
            Product.objects.filter(store=self.request.user.store)
            .select_related("store", "category")
            .prefetch_related("images", "inventory")
            .order_by("-created_at")
        )

    def perform_create(self, serializer: VendorProductSerializer) -> None:
        """Delegates to ProductService — never assigns store from input."""
        ProductService.create_product(
            store=self.request.user.store,
            validated_data=serializer.validated_data,
        )

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request: Request, pk: str | None = None) -> Response:
        """Submit a DRAFT or REJECTED product for admin review."""
        product = self.get_object()
        try:
            ProductService.submit_for_review(product=product, vendor_user=request.user)
        except InvalidProductTransitionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(VendorProductSerializer(product).data)

    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request: Request, pk: str | None = None) -> Response:
        """Archive a product (vendor-initiated)."""
        product = self.get_object()
        try:
            ProductService.archive_product(product=product, actor=request.user)
        except InvalidProductTransitionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(VendorProductSerializer(product).data)

    @action(
        detail=True,
        methods=["post"],
        url_path="images",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload_image(self, request: Request, pk: str | None = None) -> Response:
        """Upload a product image (multipart form)."""
        product = self.get_object()
        serializer = ProductImageUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            img = ProductService.add_image(
                product=product,
                image_file=serializer.validated_data["image"],
                alt_text=serializer.validated_data.get("alt_text", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"id": img.pk, "position": img.position}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path="images/(?P<image_pk>[0-9]+)")
    def delete_image(self, request: Request, pk: str | None = None, image_pk: str | None = None) -> Response:
        """Delete a specific product image."""
        product = self.get_object()
        try:
            img = product.images.get(pk=image_pk)
        except ProductImage.DoesNotExist:
            return Response({"detail": "Image not found."}, status=status.HTTP_404_NOT_FOUND)
        ProductService.delete_image(image=img, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Vendor — Dashboard
# ---------------------------------------------------------------------------

class VendorDashboardView(APIView):
    """
    Aggregated KPI dashboard for the authenticated vendor's store.

    Returns a single snapshot object — not paginated.
    Escrow and order data are joined via FK — requires escrow and orders
    apps to be installed.
    """

    permission_classes = [IsAuthenticated, IsVendor, IsStoreApproved]

    def get(self, request: Request) -> Response:
        store = request.user.store

        product_agg = store.products.aggregate(
            total=Count("id"),
            pending=Count("id", filter=Q(status=Product.Status.PENDING)),
            active=Count("id", filter=Q(status=Product.Status.APPROVED)),
        )

        # Orders pending shipment — stub until apps/orders is wired
        orders_pending_shipment = 0
        escrow_held_zmw = Decimal("0.00")
        dispute_rate_pct = Decimal("0.00")
        last_payout_at = None
        last_payout_zmw = None

        # Wire escrow / order aggregations here once those apps are available:
        # from apps.escrow.models import EscrowAccount
        # from apps.orders.models import Order
        # orders_pending_shipment = Order.objects.filter(
        #     store=store, status="CONFIRMED"
        # ).count()
        # escrow_held_zmw = EscrowAccount.objects.filter(
        #     order__store=store, state="HELD"
        # ).aggregate(total=Coalesce(Sum("balance"), Decimal("0.00")))["total"]

        data = {
            "store_name": store.name,
            "store_status": store.status,
            "total_products": product_agg["total"],
            "pending_listings": product_agg["pending"],
            "active_listings": product_agg["active"],
            "orders_pending_shipment": orders_pending_shipment,
            "escrow_held_zmw": escrow_held_zmw,
            "total_gmv_zmw": store.total_gmv,
            "dispute_rate_pct": dispute_rate_pct,
            "last_payout_at": last_payout_at,
            "last_payout_zmw": last_payout_zmw,
        }
        return Response(StoreDashboardSerializer(data).data)


# ---------------------------------------------------------------------------
# Admin — Store review
# ---------------------------------------------------------------------------

class AdminStoreViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Admin read + action endpoint for Store review.

    Actions: approve, reject, suspend
    """

    permission_classes = [IsAdminUser]
    serializer_class = AdminStoreSerializer
    queryset = Store.objects.all().select_related("owner", "approved_by")
    filterset_fields = ["status", "business_type", "payout_provider"]
    search_fields = ["name", "owner__email", "nrc_or_reg_no", "tpin"]
    ordering_fields = ["created_at", "status"]
    ordering = ["-created_at"]

    @action(detail=True, methods=["post"])
    def approve(self, request: Request, pk: str | None = None) -> Response:
        store = self.get_object()
        try:
            StoreService.approve_store(store=store, admin_user=request.user)
        except InvalidStoreTransitionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AdminStoreSerializer(store).data)

    @action(detail=True, methods=["post"])
    def reject(self, request: Request, pk: str | None = None) -> Response:
        reason = request.data.get("reason", "")
        if not reason:
            return Response(
                {"detail": "A rejection reason is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        store = self.get_object()
        try:
            StoreService.reject_store(
                store=store, admin_user=request.user, reason=reason
            )
        except (InvalidStoreTransitionError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AdminStoreSerializer(store).data)

    @action(detail=True, methods=["post"])
    def suspend(self, request: Request, pk: str | None = None) -> Response:
        reason = request.data.get("reason", "")
        if not reason:
            return Response(
                {"detail": "A suspension reason is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        store = self.get_object()
        try:
            StoreService.suspend_store(
                store=store, admin_user=request.user, reason=reason
            )
        except (InvalidStoreTransitionError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AdminStoreSerializer(store).data)


# ---------------------------------------------------------------------------
# Admin — Product review
# ---------------------------------------------------------------------------

class AdminProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Admin read + action endpoint for Product listing review.
    PENDING listings are ordered first for fast triage.
    """

    permission_classes = [IsAdminUser]
    serializer_class = AdminProductSerializer
    search_fields = ["name", "store__name"]
    filterset_fields = ["status", "store__status", "condition"]
    ordering = ["status", "-created_at"]

    def get_queryset(self):
        from django.db.models import Case, IntegerField, When

        return (
            Product.objects.all()
            .select_related("store", "category", "approved_by")
            .prefetch_related("images", "inventory")
            .order_by(
                Case(
                    When(status=Product.Status.PENDING, then=0),
                    default=1,
                    output_field=IntegerField(),
                ),
                "-created_at",
            )
        )

    @action(detail=True, methods=["post"])
    def approve(self, request: Request, pk: str | None = None) -> Response:
        product = self.get_object()
        try:
            ProductService.approve_product(
                product=product, admin_user=request.user
            )
        except InvalidProductTransitionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AdminProductSerializer(product).data)

    @action(detail=True, methods=["post"])
    def reject(self, request: Request, pk: str | None = None) -> Response:
        reason = request.data.get("reason", "")
        if not reason:
            return Response(
                {"detail": "A rejection reason is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        product = self.get_object()
        try:
            ProductService.reject_product(
                product=product, admin_user=request.user, reason=reason
            )
        except (InvalidProductTransitionError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AdminProductSerializer(product).data)
