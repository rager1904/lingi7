"""
Authenticated Lingi7 proxy for the catalog enrichment workbench.

The standalone enrichment FastAPI service remains an internal model/workflow
service. Browser clients call Django so JWT, vendor ownership, rate limiting,
and assistant indexing stay centralized.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.products.enrichment import CatalogEnrichmentService
from apps.products.models import Product

logger = logging.getLogger(__name__)


class EnrichmentWorkbenchProxy(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"
    upstream_path = ""
    upstream_method = "post"
    attach_product = False

    def get(self, request, *args: Any, **kwargs: Any):
        return self._forward(request, method="get")

    def post(self, request, *args: Any, **kwargs: Any):
        return self._forward(request, method="post")

    def delete(self, request, *args: Any, **kwargs: Any):
        return self._forward(request, method="delete")

    def _forward(self, request, *, method: str):
        base_url = str(settings.CATALOG_ENRICHMENT_SERVICE_URL).rstrip("/")
        if not base_url:
            return Response(
                {"detail": "Catalog enrichment service is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        product_id = request.data.get("product_id") if hasattr(request, "data") else None
        product = None
        if self.attach_product and product_id:
            try:
                product = self._get_owned_product(request, product_id)
            except Product.DoesNotExist:
                return Response(
                    {"detail": "Product not found or not owned by this account."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            except PermissionDenied as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)

        data = self._form_data(request)
        files = self._files(request)

        try:
            response = requests.request(
                method,
                f"{base_url}{self.upstream_path}",
                data=data if method != "get" else None,
                files=files or None,
                timeout=getattr(settings, "CATALOG_ENRICHMENT_SERVICE_TIMEOUT", 45),
            )
        except requests.RequestException as exc:
            logger.warning("Enrichment workbench proxy failed: path=%s error=%s", self.upstream_path, exc)
            return Response(
                {"detail": "Catalog enrichment service is unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if self.attach_product and response.ok and product is not None:
            attach_error = self._attach_to_product(product, response)
            if attach_error:
                return attach_error

        return self._proxy_response(response)

    def _form_data(self, request) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for key, value in request.data.items():
            if key in request.FILES or key == "product_id":
                continue
            data[key] = value
        return data

    def _files(self, request) -> list[tuple[str, tuple[str, Any, str]]]:
        files: list[tuple[str, tuple[str, Any, str]]] = []
        for key, uploaded in request.FILES.items():
            files.append(
                (
                    key,
                    (
                        uploaded.name,
                        uploaded.file,
                        uploaded.content_type or "application/octet-stream",
                    ),
                )
            )
        return files

    def _attach_to_product(self, product: Product, response: requests.Response) -> Response | None:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                CatalogEnrichmentService.apply_external_payload(product, payload)
                return None
            return Response(
                {"detail": "Enrichment service returned an invalid payload."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception as exc:
            logger.warning("Unable to attach enrichment payload to product=%s: %s", product.pk, exc)
            return Response(
                {"detail": "Enrichment completed but could not be saved to the product."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    def _get_owned_product(self, request, product_id: Any) -> Product:
        queryset = Product.objects.select_related("store", "category")
        if request.user.is_staff:
            return queryset.get(pk=product_id)
        return queryset.get(pk=product_id, store__owner=request.user)

    def _proxy_response(self, response: requests.Response):
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                return Response(response.json(), status=response.status_code)
            except ValueError:
                return Response({"detail": response.text}, status=response.status_code)
        passthrough = HttpResponse(
            response.content,
            status=response.status_code,
            content_type=content_type or "application/octet-stream",
        )
        for header in ("content-disposition", "x-glb-size-bytes", "x-artifact-id"):
            if header in response.headers:
                passthrough[header] = response.headers[header]
        return passthrough


class AnalyzeView(EnrichmentWorkbenchProxy):
    upstream_path = "/vlm/analyze"
    attach_product = True


class FaqsView(EnrichmentWorkbenchProxy):
    upstream_path = "/vlm/faqs"


class ManualExtractView(EnrichmentWorkbenchProxy):
    upstream_path = "/vlm/manual/extract"


class PoliciesView(EnrichmentWorkbenchProxy):
    upstream_path = "/policies"


class VariationView(EnrichmentWorkbenchProxy):
    upstream_path = "/generate/variation"


class Generate3DView(EnrichmentWorkbenchProxy):
    upstream_path = "/generate/3d"


class ProtocolsView(EnrichmentWorkbenchProxy):
    upstream_path = "/protocols/generate"


class ServicesHealthView(EnrichmentWorkbenchProxy):
    upstream_path = "/health/services"
