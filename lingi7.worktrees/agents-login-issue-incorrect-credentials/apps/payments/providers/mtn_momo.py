"""
apps/payments/providers/mtn_momo.py

MTN Mobile Money API v2 client for Lingi7.
Handles Collections (buyer payments) and Disbursements (vendor payouts).

API Reference: https://momodeveloper.mtn.com/
Sandbox: https://sandbox.momodeveloper.mtn.com/

All amounts in ZMW (Zambian Kwacha). MSISDN format: 260XXXXXXXXX (no +).

Doc Ref: LG7-BE-005 v1.0
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class MTNEnvironment(str, Enum):
    SANDBOX = "sandbox"
    PRODUCTION = "production"


@dataclass(frozen=True)
class MTNPaymentResult:
    """Immutable result from any MTN MoMo API call."""

    success: bool
    provider_reference: str  # MTN's financialTransactionId
    status: str  # RAW provider status string
    response_code: str
    raw_response: dict[str, Any]
    error_message: str = ""


class MTNMoMoClient:
    """
    MTN Mobile Money API v2 client.

    Handles OAuth token acquisition, collection initiation, status polling,
    and disbursements. Thread-safe — token is refreshed per-request if expired.

    Usage:
        client = MTNMoMoClient.from_settings()
        result = client.request_to_pay(
            amount=Decimal("500.00"),
            payer_msisdn="260971234567",
            reference="ORDER-abc123",
            message="Payment for Lingi7 order ORD-001",
        )
    """

    # MTN API v2 base paths
    _COLLECTION_BASE = "/collection/v1_0"
    _DISBURSEMENT_BASE = "/disbursement/v1_0"
    _TOKEN_PATH = "/token/"

    # MTN sandbox host
    _SANDBOX_HOST = "https://sandbox.momodeveloper.mtn.com"

    def __init__(
        self,
        *,
        collection_api_key: str,
        collection_user_id: str,
        disbursement_api_key: str,
        disbursement_user_id: str,
        subscription_key: str,
        environment: MTNEnvironment = MTNEnvironment.SANDBOX,
        base_url: str | None = None,
        callback_url: str | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self._collection_api_key = collection_api_key
        self._collection_user_id = collection_user_id
        self._disbursement_api_key = disbursement_api_key
        self._disbursement_user_id = disbursement_user_id
        self._subscription_key = subscription_key
        self._environment = environment
        self._base_url = base_url or self._SANDBOX_HOST
        self._callback_url = callback_url
        self._timeout = httpx.Timeout(timeout_seconds)

        # Token cache — refreshed lazily
        self._collection_token: str | None = None
        self._disbursement_token: str | None = None

    @classmethod
    def from_settings(cls) -> "MTNMoMoClient":
        """Construct from Django settings. Raises ImproperlyConfigured if missing."""
        from django.core.exceptions import ImproperlyConfigured

        required = [
            "MTN_MOMO_COLLECTION_API_KEY",
            "MTN_MOMO_COLLECTION_USER_ID",
            "MTN_MOMO_DISBURSEMENT_API_KEY",
            "MTN_MOMO_DISBURSEMENT_USER_ID",
            "MTN_MOMO_SUBSCRIPTION_KEY",
        ]
        for key in required:
            if not getattr(settings, key, None):
                raise ImproperlyConfigured(
                    f"MTN MoMo setting {key} is not configured."
                )

        env_str = getattr(settings, "MTN_MOMO_ENVIRONMENT", "sandbox")
        env = MTNEnvironment(env_str)

        return cls(
            collection_api_key=settings.MTN_MOMO_COLLECTION_API_KEY,
            collection_user_id=settings.MTN_MOMO_COLLECTION_USER_ID,
            disbursement_api_key=settings.MTN_MOMO_DISBURSEMENT_API_KEY,
            disbursement_user_id=settings.MTN_MOMO_DISBURSEMENT_USER_ID,
            subscription_key=settings.MTN_MOMO_SUBSCRIPTION_KEY,
            environment=env,
            base_url=getattr(settings, "MTN_MOMO_BASE_URL", None),
            callback_url=getattr(settings, "MTN_MOMO_CALLBACK_URL", None),
        )

    # ------------------------------------------------------------------ #
    # Token management                                                     #
    # ------------------------------------------------------------------ #

    def _get_collection_token(self) -> str:
        """Obtain or refresh OAuth2 collection token."""
        if self._collection_token:
            return self._collection_token
        self._collection_token = self._fetch_token(
            product_path=self._COLLECTION_BASE,
            api_user_id=self._collection_user_id,
            api_key=self._collection_api_key,
        )
        return self._collection_token

    def _get_disbursement_token(self) -> str:
        """Obtain or refresh OAuth2 disbursement token."""
        if self._disbursement_token:
            return self._disbursement_token
        self._disbursement_token = self._fetch_token(
            product_path=self._DISBURSEMENT_BASE,
            api_user_id=self._disbursement_user_id,
            api_key=self._disbursement_api_key,
        )
        return self._disbursement_token

    def _fetch_token(
        self,
        product_path: str,
        api_user_id: str,
        api_key: str,
    ) -> str:
        """POST to /token/ and return the access_token string."""
        url = f"{self._base_url}{product_path}{self._TOKEN_PATH}"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    url,
                    auth=(api_user_id, api_key),
                    headers={
                        "Ocp-Apim-Subscription-Key": self._subscription_key,
                        "Content-Type": "application/json",
                    },
                )
            resp.raise_for_status()
            token = resp.json()["access_token"]
            logger.debug("MTN MoMo token acquired for %s", product_path)
            return token
        except httpx.HTTPError as exc:
            logger.error("MTN MoMo token acquisition failed: %s", exc)
            raise MTNMoMoError(f"Token acquisition failed: {exc}") from exc

    def _collection_headers(self, reference_id: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_collection_token()}",
            "X-Reference-Id": reference_id,
            "X-Target-Environment": self._environment.value,
            "Ocp-Apim-Subscription-Key": self._subscription_key,
            "Content-Type": "application/json",
        }

    def _disbursement_headers(self, reference_id: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_disbursement_token()}",
            "X-Reference-Id": reference_id,
            "X-Target-Environment": self._environment.value,
            "Ocp-Apim-Subscription-Key": self._subscription_key,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------ #
    # Collections (buyer payments)                                         #
    # ------------------------------------------------------------------ #

    def request_to_pay(
        self,
        *,
        amount: Decimal,
        payer_msisdn: str,
        reference: str,
        message: str,
        idempotency_key: str | None = None,
    ) -> MTNPaymentResult:
        """
        Initiate a collection (buyer pays via USSD prompt).

        Args:
            amount: Payment amount in ZMW. Must be > 0.
            payer_msisdn: Buyer's phone without +. E.g. "260971234567".
            reference: Platform order/escrow reference. Shown to payer.
            message: Description shown in USSD prompt. Max 50 chars.
            idempotency_key: Unique UUID for this attempt. Generated if None.

        Returns:
            MTNPaymentResult. On success, status is "PENDING" — confirmed
            later via webhook or polling.
        """
        ref_id = idempotency_key or str(uuid.uuid4())
        url = f"{self._base_url}{self._COLLECTION_BASE}/requesttopay"

        payload: dict[str, Any] = {
            "amount": str(amount),
            "currency": "ZMW",
            "externalId": reference,
            "payer": {
                "partyIdType": "MSISDN",
                "partyId": payer_msisdn,
            },
            "payerMessage": message[:50],
            "payeeNote": reference[:50],
        }

        if self._callback_url:
            headers = self._collection_headers(ref_id)
            headers["X-Callback-Url"] = self._callback_url
        else:
            headers = self._collection_headers(ref_id)

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(url, headers=headers, json=payload)

            logger.info(
                "MTN requesttopay sent ref=%s status=%d",
                ref_id,
                resp.status_code,
            )

            if resp.status_code == 202:
                # Accepted — payment request queued by MTN
                return MTNPaymentResult(
                    success=True,
                    provider_reference=ref_id,
                    status="PENDING",
                    response_code="202",
                    raw_response={"reference_id": ref_id},
                )

            # Non-202 is a failure
            error_body: dict[str, Any] = {}
            try:
                error_body = resp.json()
            except Exception:
                error_body = {"raw": resp.text}

            logger.warning(
                "MTN requesttopay failed ref=%s code=%d body=%s",
                ref_id,
                resp.status_code,
                error_body,
            )
            return MTNPaymentResult(
                success=False,
                provider_reference=ref_id,
                status="FAILED",
                response_code=str(resp.status_code),
                raw_response=error_body,
                error_message=error_body.get("message", "Request to pay failed"),
            )

        except httpx.TimeoutException as exc:
            logger.error("MTN requesttopay timeout ref=%s: %s", ref_id, exc)
            self._collection_token = None  # Force token refresh on next call
            return MTNPaymentResult(
                success=False,
                provider_reference=ref_id,
                status="TIMEOUT",
                response_code="TIMEOUT",
                raw_response={},
                error_message=str(exc),
            )
        except httpx.HTTPError as exc:
            logger.error("MTN requesttopay error ref=%s: %s", ref_id, exc)
            self._collection_token = None
            return MTNPaymentResult(
                success=False,
                provider_reference=ref_id,
                status="FAILED",
                response_code="HTTP_ERROR",
                raw_response={},
                error_message=str(exc),
            )

    def get_payment_status(self, reference_id: str) -> MTNPaymentResult:
        """
        Poll the status of a previously initiated requesttopay.

        Args:
            reference_id: The X-Reference-Id used in the original request.

        Returns:
            MTNPaymentResult with status SUCCESSFUL, FAILED, or PENDING.
        """
        url = f"{self._base_url}{self._COLLECTION_BASE}/requesttopay/{reference_id}"
        headers = {
            "Authorization": f"Bearer {self._get_collection_token()}",
            "X-Target-Environment": self._environment.value,
            "Ocp-Apim-Subscription-Key": self._subscription_key,
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(url, headers=headers)

            body: dict[str, Any] = {}
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text}

            if resp.status_code == 200:
                mtn_status = body.get("status", "PENDING")
                financial_txn_id = body.get("financialTransactionId", reference_id)
                return MTNPaymentResult(
                    success=(mtn_status == "SUCCESSFUL"),
                    provider_reference=financial_txn_id,
                    status=mtn_status,
                    response_code="200",
                    raw_response=body,
                )

            return MTNPaymentResult(
                success=False,
                provider_reference=reference_id,
                status="FAILED",
                response_code=str(resp.status_code),
                raw_response=body,
                error_message=body.get("message", "Status poll failed"),
            )

        except httpx.HTTPError as exc:
            logger.error("MTN status poll failed ref=%s: %s", reference_id, exc)
            self._collection_token = None
            return MTNPaymentResult(
                success=False,
                provider_reference=reference_id,
                status="FAILED",
                response_code="HTTP_ERROR",
                raw_response={},
                error_message=str(exc),
            )

    # ------------------------------------------------------------------ #
    # Disbursements (vendor payouts)                                       #
    # ------------------------------------------------------------------ #

    def transfer(
        self,
        *,
        amount: Decimal,
        payee_msisdn: str,
        reference: str,
        message: str,
        idempotency_key: str | None = None,
    ) -> MTNPaymentResult:
        """
        Initiate a disbursement (platform pays out to vendor MoMo account).

        Args:
            amount: Payout amount in ZMW after platform fee deduction.
            payee_msisdn: Vendor's MoMo number without +.
            reference: Escrow account reference (PAYOUT-{escrow_id}).
            message: Note stored against the transaction.
            idempotency_key: Unique UUID. Generated if None.

        Returns:
            MTNPaymentResult. Success means disbursement was accepted (202).
        """
        ref_id = idempotency_key or str(uuid.uuid4())
        url = f"{self._base_url}{self._DISBURSEMENT_BASE}/transfer"

        payload: dict[str, Any] = {
            "amount": str(amount),
            "currency": "ZMW",
            "externalId": reference,
            "payee": {
                "partyIdType": "MSISDN",
                "partyId": payee_msisdn,
            },
            "payerMessage": message[:50],
            "payeeNote": reference[:50],
        }

        headers = self._disbursement_headers(ref_id)

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(url, headers=headers, json=payload)

            logger.info(
                "MTN transfer sent ref=%s status=%d",
                ref_id,
                resp.status_code,
            )

            if resp.status_code == 202:
                return MTNPaymentResult(
                    success=True,
                    provider_reference=ref_id,
                    status="PENDING",
                    response_code="202",
                    raw_response={"reference_id": ref_id},
                )

            error_body: dict[str, Any] = {}
            try:
                error_body = resp.json()
            except Exception:
                error_body = {"raw": resp.text}

            logger.error(
                "MTN transfer failed ref=%s code=%d body=%s",
                ref_id,
                resp.status_code,
                error_body,
            )
            return MTNPaymentResult(
                success=False,
                provider_reference=ref_id,
                status="FAILED",
                response_code=str(resp.status_code),
                raw_response=error_body,
                error_message=error_body.get("message", "Transfer failed"),
            )

        except httpx.TimeoutException as exc:
            logger.error("MTN transfer timeout ref=%s: %s", ref_id, exc)
            self._disbursement_token = None
            return MTNPaymentResult(
                success=False,
                provider_reference=ref_id,
                status="TIMEOUT",
                response_code="TIMEOUT",
                raw_response={},
                error_message=str(exc),
            )
        except httpx.HTTPError as exc:
            logger.error("MTN transfer error ref=%s: %s", ref_id, exc)
            self._disbursement_token = None
            return MTNPaymentResult(
                success=False,
                provider_reference=ref_id,
                status="FAILED",
                response_code="HTTP_ERROR",
                raw_response={},
                error_message=str(exc),
            )


class MTNMoMoError(Exception):
    """Raised for unrecoverable MTN MoMo API errors."""
