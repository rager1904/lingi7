"""
Unified AI API gateway for the marketplace platform.

These views keep Django as the single authenticated entry point while delegating
model-heavy work to local open-source services when available. Every endpoint
falls back to database-backed behavior so buyers are not blocked by an AI worker
restart.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from django.conf import settings
from django.db import connection
from django.db.models import Count, Q
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.currency import get_usd_to_zmw_rate
from apps.orders.models import OrderLine
from apps.products.models import Category, Product, Store
from apps.products.serializers import PublicProductListSerializer

logger = logging.getLogger(__name__)

_NUMBER = r"[0-9][0-9,]*\.?[0-9]*"
_USD_PREFIX_RE = re.compile(r"(?i)(?<!\w)(US\$|USD|\$)\s*(" + _NUMBER + r")(?![\w$])")
_USD_SUFFIX_RE = re.compile(r"(?i)(?<![\w$])(" + _NUMBER + r")\s*(USD|US\$)(?!\w)")


def _zmw_rate() -> float:
    return get_usd_to_zmw_rate()


def _usd_to_zmw(text: str) -> str:
    """Convert any US-dollar price expressions in text to Zambian Kwacha.

    Deterministic safety net for the LLM: rewrites "$799", "US$799" or
    "USD 799" (and the same with trailing "USD") to "K 21,573.00" using the
    configured rate. Left untouched when no dollar amount is present.
    """

    def rep_prefix(match: re.Match) -> str:
        try:
            amount = float(match.group(2).replace(",", ""))
        except (TypeError, ValueError):
            return match.group(0)
        return f"K {amount * _zmw_rate():,.2f}"

    def rep_suffix(match: re.Match) -> str:
        try:
            amount = float(match.group(1).replace(",", ""))
        except (TypeError, ValueError):
            return match.group(0)
        return f"K {amount * _zmw_rate():,.2f}"

    return _USD_SUFFIX_RE.sub(rep_suffix, _USD_PREFIX_RE.sub(rep_prefix, text))


def _normalize_price(value: Any) -> str:
    """Convert a raw product price string (possibly USD) to a numeric ZMW string.

    Product-card prices rendered by the assistant may arrive as "$799",
    "USD 799" or plain ZMW numbers. Returned as a plain decimal, e.g. "21573.00",
    so the frontend renders it with the Kwacha symbol.
    """
    if value is None:
        return "0.00"
    cleaned = re.sub(r"(?i)[$\s,]|US\$|USD", "", str(value))
    try:
        amount = float(cleaned)
    except (TypeError, ValueError):
        return str(value)
    return f"{amount * _zmw_rate():.2f}"


def _visible_products():
    return (
        Product.objects.filter(
            status=Product.Status.APPROVED,
            store__status=Store.Status.APPROVED,
        )
        .select_related("store", "category")
        .prefetch_related("images", "inventory")
    )


def _response(data: Any, *, source: str = "database", meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "success": True,
        "source": source,
        "data": data,
        "meta": meta or {},
    }


def _serialize_products(products, request) -> list[dict[str, Any]]:
    return PublicProductListSerializer(products, many=True, context={"request": request}).data


def _decimal_param(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise serializers.ValidationError("Price filters must be valid decimal values.")


class ProductSearchSerializer(serializers.Serializer):
    query = serializers.CharField(max_length=500)
    category = serializers.CharField(max_length=140, required=False, allow_blank=True)
    min_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    max_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    condition = serializers.CharField(max_length=20, required=False, allow_blank=True)
    limit = serializers.IntegerField(min_value=1, max_value=20, default=8)


class AssistantQuerySerializer(serializers.Serializer):
    query = serializers.CharField(max_length=2000)
    context = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    image = serializers.CharField(required=False, allow_blank=True)
    guardrails = serializers.BooleanField(default=True)


class SemanticProductSearchView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"

    def post(self, request) -> Response:
        serializer = ProductSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data

        products = self._database_search(
            query=params["query"],
            category=params.get("category", ""),
            min_price=params.get("min_price"),
            max_price=params.get("max_price"),
            condition=params.get("condition", ""),
            limit=params["limit"],
        )
        source = "database"

        retriever_ids = self._semantic_ids(params)
        if retriever_ids:
            ranked = self._products_for_retriever_ids(retriever_ids, params["limit"])
            if ranked:
                products = ranked
                source = "catalog-retriever"

        return Response(_response(_serialize_products(products, request), source=source))

    def _semantic_ids(self, params: dict[str, Any]) -> list[str]:
        payload = {
            "text": [params["query"]],
            "categories": self._retriever_categories(params.get("category", "")),
            "filters": {
                "min_price": str(params["min_price"]) if params.get("min_price") is not None else None,
                "max_price": str(params["max_price"]) if params.get("max_price") is not None else None,
            },
            "k": params["limit"],
        }
        try:
            response = requests.post(
                f"{settings.CATALOG_RETRIEVER_URL.rstrip('/')}/query/text",
                json=payload,
                timeout=settings.CATALOG_RETRIEVER_TIMEOUT,
            )
            response.raise_for_status()
            ids = response.json().get("ids", [])
            return [str(item) for group in ids for item in (group if isinstance(group, list) else [group])]
        except Exception as exc:
            logger.warning("Catalog retriever search failed; using DB fallback: %s", exc)
            return []

    def _retriever_categories(self, category: str) -> list[str]:
        if category:
            return [category]
        return list(Category.objects.filter(is_active=True).values_list("slug", flat=True)[:50])

    def _products_for_retriever_ids(self, retriever_ids: list[str], limit: int) -> list[Product]:
        pks: list[int] = []
        for value in retriever_ids:
            if value.isdigit():
                pks.append(int(value))
        if not pks:
            return []

        products_by_id = {product.pk: product for product in _visible_products().filter(pk__in=pks)}
        return [products_by_id[pk] for pk in pks if pk in products_by_id][:limit]

    def _database_search(
        self,
        *,
        query: str,
        category: str,
        min_price: Decimal | None,
        max_price: Decimal | None,
        condition: str,
        limit: int,
    ):
        text_q = (
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(meta_title__icontains=query)
            | Q(meta_description__icontains=query)
        )
        if connection.vendor != "sqlite":
            text_q |= Q(search_keywords__icontains=query) | Q(suggested_tags__icontains=query)
        qs = _visible_products().filter(text_q)
        if category:
            qs = qs.filter(Q(category__slug=category) | Q(category__name__iexact=category))
        if min_price is not None:
            qs = qs.filter(price__gte=min_price)
        if max_price is not None:
            qs = qs.filter(price__lte=max_price)
        if condition:
            qs = qs.filter(condition=condition)
        return list(qs.order_by("-created_at")[:limit])


class ProductRecommendationView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"

    def get(self, request) -> Response:
        try:
            limit = max(1, min(int(request.query_params.get("limit", 8)), 20))
        except (ValueError, TypeError):
            limit = 8
        purchased_names = list(
            OrderLine.objects.filter(order__buyer=request.user)
            .values("product_name")
            .annotate(count=Count("id"))
            .order_by("-count")
            .values_list("product_name", flat=True)[:20]
        )

        category_ids = set()
        if purchased_names:
            category_ids.update(
                _visible_products()
                .filter(name__in=purchased_names)
                .values_list("category_id", flat=True)
            )

        qs = _visible_products()
        if category_ids:
            qs = qs.filter(category_id__in=category_ids)
            source = "purchase-history"
        else:
            source = "newest-products"

        products = list(qs.order_by("-created_at")[:limit])
        return Response(_response(_serialize_products(products, request), source=source))


class SimilarProductView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"

    def get(self, request, product_id: int) -> Response:
        try:
            limit = max(1, min(int(request.query_params.get("limit", 8)), 20))
        except (ValueError, TypeError):
            limit = 8
        try:
            product = _visible_products().get(pk=product_id)
        except Product.DoesNotExist:
            return Response({"success": False, "detail": "Product not found."}, status=status.HTTP_404_NOT_FOUND)

        if connection.vendor != "sqlite":
            tag_filter = Q()
            for tag in product.suggested_tags[:8]:
                tag_filter |= Q(suggested_tags__icontains=tag)
            qs = _visible_products().exclude(pk=product.pk).filter(Q(category=product.category) | tag_filter)
        else:
            qs = _visible_products().exclude(pk=product.pk).filter(category=product.category)
        products = list(qs.order_by("price", "-created_at")[:limit])
        return Response(_response(_serialize_products(products, request), source="product-similarity"))


class AssistantQueryView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "assistant"

    def post(self, request) -> Response:
        serializer = AssistantQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payload = {
            "user_id": (
                str(request.user.pk) if request.user.is_authenticated else "anonymous"
            ),
            "query": data["query"],
            "context": data.get("context", ""),
            "image": data.get("image", ""),
            "guardrails": data.get("guardrails", True),
            "image_bool": bool(data.get("image")),
        }
        try:
            response = requests.post(
                f"{settings.ASSISTANT_CHAIN_URL.rstrip('/')}/query/timing",
                json=payload,
                timeout=settings.ASSISTANT_CHAIN_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            source = "shopping-assistant"
            if isinstance(payload, dict):
                if isinstance(payload.get("response"), str):
                    payload["response"] = _usd_to_zmw(payload["response"])
                products = payload.get("products")
                if isinstance(products, list):
                    for item in products:
                        if isinstance(item, dict) and "price" in item:
                            item["price"] = _normalize_price(item.get("price"))

                # Ground in the Django database whenever the semantic retriever
                # came back empty, so the reply can never hallucinate inventory
                # that the marketplace does not actually hold.
                intent = str(payload.get("intent", "")).strip().lower()
                if intent == "retriever" and not products:
                    grounded = self._database_ground(data["query"], request)
                    if grounded:
                        payload["products"] = grounded
                        names = ", ".join(item["name"] for item in grounded)
                        payload["response"] = (
                            "Here are matching products from the marketplace "
                            f"catalog: {names}."
                        )
                        source = "database-grounding"
            return Response(_response(payload, source=source))
        except Exception as exc:
            logger.warning("Shopping assistant service failed; using fallback response: %s", exc)
            grounded = self._database_ground(data["query"], request)
            names = ", ".join(item["name"] for item in grounded)
            return Response(
                _response(
                    {
                        "response": (
                            "The assistant service is temporarily unavailable. "
                            "Here are matching products from the marketplace catalog"
                            + (f": {names}." if names else ".")
                        ),
                        "products": grounded,
                        "timings": {},
                    },
                    source="database-fallback",
                ),
                status=status.HTTP_200_OK,
            )

    def _database_ground(self, query: str, request, limit: int = 5) -> list[dict[str, Any]]:
        """Ground an assistant reply in real, visible Django products.

        Used when the semantic retriever returns nothing so the reply can never
        invent inventory. Token-based so multi-word queries ("girls button up
        cardigan") still match, and falls back to the newest live products for
        pure browse requests ("what do you have").
        """
        stop = {
            "the", "and", "for", "you", "your", "show", "have", "what", "whats",
            "with", "want", "need", "me", "my", "any", "some", "available", "is",
            "are", "of", "to", "in", "on", "do", "does", "looking", "find", "get",
            "please", "can", "could", "would", "there", "this", "that",
        }
        tokens = re.findall(r"[A-Za-z0-9']+", query or "")
        terms = [t for t in tokens if len(t) > 2 and t.lower() not in stop][:6]

        qs = _visible_products()
        matches: list[Product] = []
        if terms:
            text_q = Q()
            for term in terms:
                text_q |= Q(name__icontains=term) | Q(description__icontains=term)
            if connection.vendor != "sqlite":
                for term in terms:
                    text_q |= Q(search_keywords__icontains=term)
            matches = list(qs.filter(text_q).order_by("-created_at")[:limit])
        if not matches:
            matches = list(qs.order_by("-created_at")[:limit])

        return [
            {
                "name": item["name"],
                "price": str(item["price"]),
                "image": item.get("primary_image") or "",
                "pk": str(item["id"]),
            }
            for item in _serialize_products(matches, request)
        ]
