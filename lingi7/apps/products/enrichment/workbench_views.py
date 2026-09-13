"""
Authenticated Lingi7 proxy for the catalog enrichment workbench.

The standalone enrichment FastAPI service remains an internal model/workflow
service. Browser clients call Django so JWT, vendor ownership, rate limiting,
and assistant indexing stay centralized.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

import requests
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.db import close_old_connections
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.products.enrichment import CatalogEnrichmentService
from apps.products.models import EnrichmentJob, Product
from apps.products.permissions import IsVendor
from apps.users.permissions import IsAdmin

logger = logging.getLogger(__name__)

INTERNAL_KEY_HEADER = "X-Internal-Api-Key"


class EnrichmentWorkbenchProxy(APIView):
    permission_classes = [IsAuthenticated, IsVendor | IsAdmin]
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

        internal_key = getattr(settings, "INTERNAL_API_KEY", "")
        if not internal_key:
            return Response(
                {"detail": "Catalog enrichment service is not configured for internal calls."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        headers = {INTERNAL_KEY_HEADER: internal_key}

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
                headers=headers,
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


def _run_analyze_job(job_id: int) -> None:
    """Background worker that executes a queued VLM analyze request.

    Runs in a daemon thread so long-running CPU inference never blocks the
    request that created the job. The UI polls the job until it resolves.
    """
    close_old_connections()
    job = EnrichmentJob.objects.filter(pk=job_id).first()
    if job is None:
        return
    job.status = EnrichmentJob.Status.PROCESSING
    job.attempts += 1
    job.save(update_fields=["status", "attempts", "updated_at"])

    base_url = str(settings.CATALOG_ENRICHMENT_SERVICE_URL).rstrip("/")
    try:
        headers = {INTERNAL_KEY_HEADER: settings.INTERNAL_API_KEY}
        data: dict[str, Any] = {"locale": job.locale}
        if job.product_data is not None:
            data["product_data"] = json.dumps(job.product_data)
        if job.brand_instructions:
            data["brand_instructions"] = job.brand_instructions

        image_path = Path(job.image.path) if job.image else None
        if image_path is not None and image_path.exists():
            files = [("image", (image_path.name, image_path.open("rb"), "image/jpeg"))]
        else:
            files = None

        timeout = getattr(settings, "CATALOG_ENRICHMENT_SERVICE_TIMEOUT", 45)
        response = requests.post(
            f"{base_url}/vlm/analyze",
            headers=headers,
            data=data,
            files=files,
            timeout=timeout,
        )

        if response.ok:
            payload = response.json()
            if job.product_id:
                try:
                    CatalogEnrichmentService.apply_external_payload(job.product, payload)
                except Exception as exc:
                    logger.warning(
                        "Enrichment job=%s could not attach payload: %s", job.pk, exc
                    )
            job.result = payload
            job.status = EnrichmentJob.Status.RESOLVED
        else:
            job.error = (
                f"Enrichment service error {response.status_code}: "
                f"{response.text[:500]}"
            )
            job.status = EnrichmentJob.Status.FAILED
    except Exception as exc:
        logger.exception("Enrichment job=%s failed: %s", job.pk, exc)
        job.error = str(exc)[:2000]
        job.status = EnrichmentJob.Status.FAILED
    finally:
        job.save(update_fields=["status", "result", "error", "updated_at"])
        if files:
            for _, handle in files:
                handle[1].close()
        close_old_connections()


class AnalyzeJobCreateView(APIView):
    """
    POST /api/v1/products/enrichment-workbench/analyze-jobs/

    Queue an image so the VLM/LLM pipeline can fill product fields asynchronously.
    Returns immediately with a job id; poll the detail endpoint for the result.
    """

    permission_classes = [IsAuthenticated, IsVendor | IsAdmin]

    def post(self, request, *args: Any, **kwargs: Any) -> Response:
        uploaded = request.FILES.get("image")
        if uploaded is None:
            return Response(
                {"detail": "An image is required."}, status=status.HTTP_400_BAD_REQUEST
            )
        if uploaded.size > 10 * 1024 * 1024:
            return Response(
                {"detail": "Image must be smaller than 10MB."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        product_id_raw = request.data.get("product_id")
        product = None
        if product_id_raw:
            try:
                product_id = int(product_id_raw)
                queryset = Product.objects.all()
                if not request.user.is_staff:
                    queryset = queryset.filter(store__owner=request.user)
                product = queryset.filter(pk=product_id).first()
            except (TypeError, ValueError):
                product = None

        product_data = request.data.get("product_data")
        if isinstance(product_data, str):
            try:
                product_data = json.loads(product_data)
            except ValueError:
                product_data = None
        if not isinstance(product_data, dict):
            product_data = None

        job = EnrichmentJob.objects.create(
            owner=request.user,
            product=product,
            locale=request.data.get("locale", "en-US") or "en-US",
            product_data=product_data,
            brand_instructions=request.data.get("brand_instructions", "") or "",
            status=EnrichmentJob.Status.PENDING,
        )
        job.image.save(f"encode-{job.pk}", ContentFile(uploaded.read()))

        threading.Thread(target=_run_analyze_job, args=(job.pk,), daemon=True).start()

        return Response(
            {"job_id": job.pk, "status": job.status},
            status=status.HTTP_201_CREATED,
        )


class AnalyzeJobDetailView(APIView):
    """
    GET /api/v1/products/enrichment-workbench/analyze-jobs/{pk}/

    Return job state. Once RESOLVED, `result` carries the extracted fields.
    """

    permission_classes = [IsAuthenticated, IsVendor | IsAdmin]

    def get(self, request, pk: int, *args: Any, **kwargs: Any) -> Response:
        queryset = EnrichmentJob.objects.select_related("product")
        if not request.user.is_staff:
            queryset = queryset.filter(owner=request.user)
        job = get_object_or_404(queryset, pk=pk)

        payload: dict[str, Any] = {"job_id": job.pk, "status": job.status}
        if job.status == EnrichmentJob.Status.RESOLVED:
            payload["result"] = job.result
        if job.status == EnrichmentJob.Status.FAILED:
            payload["error"] = job.error
        return Response(payload)
