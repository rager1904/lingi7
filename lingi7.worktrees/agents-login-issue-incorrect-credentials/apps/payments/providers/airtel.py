"""
apps/payments/providers/airtel.py

Airtel Money API client for Lingi7.
Handles Collections (buyer payments) and Disbursements (vendor payouts).

API Reference: https://developers.airtel.africa/
Sandbox: https://openapiuat.airtel.africa/

All amounts in ZMW. MSISDN format: 260XXXXXXXXX (no +, no 0 prefix).

Doc Ref: LG7-BE-005 v1.0
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AirtelPaymentResult:
    """Immutable result from any Airtel Money API call."""

    success: bool
    provider_reference: str
    status: str  # TS (success), TF (failed), TP (pending)
    response_code: str
    raw_response: dict[str, Any]
    error_message: str = ""


class AirtelMoneyClient:
    """
    Airtel Money API client for collections and disbursements.

    Airtel uses OAuth2 client credentials flow for authentication.
    Status codes: TS = Transaction Successful, TF = Transaction Failed,
    TP = Transaction Pending.

    Usage:
        client = AirtelMoneyClient.from_settings()
        result = client.request_payment(
            amount=Decimal("250.00"),
            msisdn="260977654321",
            reference="ORDER-xyz789",
            transaction_id="LINGI-20240101-001",
        )
    """

    _SANDBOX_HOST = "https://openapiuat.airtel.africa"
    _PRODUCTION_HOST = "https://openapi.airtel.africa"

    _TOKEN_PATH = "/auth/oauth2/token"
    _COLLECTION_PATH = "/merchant/v2/payments/"
    _COLLECTION_STATUS_PATH = "/standard/v1/payments/"
    _DISBURSEMENT_PATH = "/standard/v1/disbursements/"
    _DISBURSEMENT_STATUS_PATH = "/standard/v1/disbursements/"

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        environment: str = "sandbox",
        base_url: str | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._is_sandbox = environment == "sandbox"
        self._base_url = base_url or (
            self._SANDBOX_HOST if self._is_sandbox else self._PRODUCTION_HOST
        )
        self._timeout = httpx.Timeout(timeout_seconds)
        self._access_token: str | None = None

    @classmethod
    def from_settings(cls) -> "AirtelMoneyClient":
        """Construct from Django settings."""
        from django.core.exceptions import ImproperlyConfigured

        for key in ["AIRTEL_MONEY_CLIENT_ID", "AIRTEL_MONEY_CLIENT_SECRET"]:
            if not getattr(settings, key, None):
                raise ImproperlyConfigured(f"Airtel Money setting {key} is not configured.")

        return cls(
            client_id=settings.AIRTEL_MONEY_CLIENT_ID,
            client_secret=settings.AIRTEL_MONEY_CLIENT_SECRET,
            environment=getattr(settings, "AIRTEL_MONEY_ENVIRONMENT", "sandbox"),
            base_url=getattr(settings, "AIRTEL_MONEY_BASE_URL", None),
        )

    # ------------------------------------------------------------------ #
    # Token management                                                     #
    # ------------------------------------------------------------------ #

    def _get_token(self) -> str:
        """Obtain or return cached OAuth2 access token."""
        if self._access_token:
            return self._access_token
        self._access_token = self._fetch_token()
        return self._access_token

    def _fetch_token(self) -> str:
        """POST to Airtel OAuth2 endpoint and return access token."""
        url = f"{self._base_url}{self._TOKEN_PATH}"
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "client_credentials",
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
            resp.raise_for_status()
            token = resp.json()["access_token"]
            logger.debug("Airtel Money token acquired")
            return token
        except httpx.HTTPError as exc:
            logger.error("Airtel token acquisition failed: %s", exc)
            raise AirtelMoneyError(f"Token acquisition failed: {exc}") from exc

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Country": "ZM",
            "X-Currency": "ZMW",
        }

    # ------------------------------------------------------------------ #
    # Collections                                                          #
    # ------------------------------------------------------------------ #

    def request_payment(
        self,
        *,
        amount: Decimal,
        msisdn: str,
        reference: str,
        transaction_id: str | None = None,
    ) -> AirtelPaymentResult:
        """
        Initiate a payment collection from a buyer's Airtel Money wallet.

        Args:
            amount: Amount in ZMW.
            msisdn: Buyer's phone number without +. E.g. "260977654321".
            reference: Platform reference shown to the user.
            transaction_id: Unique transaction ID for idempotency. Generated if None.

        Returns:
            AirtelPaymentResult. Status TP = pending confirmation via webhook.
        """
        txn_id = transaction_id or str(uuid.uuid4()).replace("-", "")[:20]
        url = f"{self._base_url}{self._COLLECTION_PATH}"

        payload: dict[str, Any] = {
            "reference": reference[:20],
            "subscriber": {
                "country": "ZM",
                "currency": "ZMW",
                "msisdn": msisdn,
            },
            "transaction": {
                "amount": str(amount),
                "country": "ZM",
                "currency": "ZMW",
                "id": txn_id,
            },
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(url, headers=self._auth_headers(), json=payload)

            body: dict[str, Any] = {}
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text}

            logger.info(
                "Airtel request_payment txn=%s status=%d",
                txn_id,
                resp.status_code,
            )

            if resp.status_code == 200:
                status_code = body.get("status", {}).get("code", "")
                is_success = status_code in ("200", "DP00800001006", "TS")
                # Airtel returns 200 for queued payments too
                airtel_ref = body.get("data", {}).get("transaction", {}).get("id", txn_id)

                return AirtelPaymentResult(
                    success=True,  # Accepted for processing
                    provider_reference=airtel_ref,
                    status="TP",  # Pending — confirmed via webhook
                    response_code=str(resp.status_code),
                    raw_response=body,
                )

            # Handle token expiry
            if resp.status_code == 401:
                self._access_token = None
                logger.warning("Airtel token expired, cleared for refresh")

            return AirtelPaymentResult(
                success=False,
                provider_reference=txn_id,
                status="TF",
                response_code=str(resp.status_code),
                raw_response=body,
                error_message=body.get("status", {}).get("message", "Payment failed"),
            )

        except httpx.TimeoutException as exc:
            logger.error("Airtel request_payment timeout txn=%s: %s", txn_id, exc)
            self._access_token = None
            return AirtelPaymentResult(
                success=False,
                provider_reference=txn_id,
                status="TIMEOUT",
                response_code="TIMEOUT",
                raw_response={},
                error_message=str(exc),
            )
        except httpx.HTTPError as exc:
            logger.error("Airtel request_payment error txn=%s: %s", txn_id, exc)
            self._access_token = None
            return AirtelPaymentResult(
                success=False,
                provider_reference=txn_id,
                status="TF",
                response_code="HTTP_ERROR",
                raw_response={},
                error_message=str(exc),
            )

    def get_payment_status(self, transaction_id: str) -> AirtelPaymentResult:
        """
        Poll the status of a previously initiated collection.

        Args:
            transaction_id: The transaction.id used in the original request.
        """
        url = f"{self._base_url}{self._COLLECTION_STATUS_PATH}{transaction_id}"

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(url, headers=self._auth_headers())

            body: dict[str, Any] = {}
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text}

            if resp.status_code == 200:
                txn_status = body.get("data", {}).get("transaction", {}).get("status", "TP")
                return AirtelPaymentResult(
                    success=(txn_status == "TS"),
                    provider_reference=transaction_id,
                    status=txn_status,
                    response_code="200",
                    raw_response=body,
                )

            return AirtelPaymentResult(
                success=False,
                provider_reference=transaction_id,
                status="TF",
                response_code=str(resp.status_code),
                raw_response=body,
                error_message="Status poll failed",
            )

        except httpx.HTTPError as exc:
            logger.error("Airtel status poll failed txn=%s: %s", transaction_id, exc)
            self._access_token = None
            return AirtelPaymentResult(
                success=False,
                provider_reference=transaction_id,
                status="TF",
                response_code="HTTP_ERROR",
                raw_response={},
                error_message=str(exc),
            )

    # ------------------------------------------------------------------ #
    # Disbursements                                                        #
    # ------------------------------------------------------------------ #

    def disburse(
        self,
        *,
        amount: Decimal,
        msisdn: str,
        reference: str,
        transaction_id: str | None = None,
    ) -> AirtelPaymentResult:
        """
        Initiate a disbursement to a vendor's Airtel Money account.

        Args:
            amount: Payout amount in ZMW.
            msisdn: Vendor's Airtel number without +.
            reference: Escrow payout reference.
            transaction_id: Unique idempotency ID. Generated if None.
        """
        txn_id = transaction_id or str(uuid.uuid4()).replace("-", "")[:20]
        url = f"{self._base_url}{self._DISBURSEMENT_PATH}"

        payload: dict[str, Any] = {
            "payee": {
                "msisdn": msisdn,
            },
            "reference": reference[:20],
            "pin": getattr(settings, "AIRTEL_MONEY_DISBURSEMENT_PIN", ""),
            "transaction": {
                "amount": str(amount),
                "id": txn_id,
                "type": "B2C",
            },
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(url, headers=self._auth_headers(), json=payload)

            body: dict[str, Any] = {}
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text}

            logger.info("Airtel disburse txn=%s status=%d", txn_id, resp.status_code)

            if resp.status_code == 200:
                return AirtelPaymentResult(
                    success=True,
                    provider_reference=txn_id,
                    status="TP",
                    response_code="200",
                    raw_response=body,
                )

            if resp.status_code == 401:
                self._access_token = None

            return AirtelPaymentResult(
                success=False,
                provider_reference=txn_id,
                status="TF",
                response_code=str(resp.status_code),
                raw_response=body,
                error_message=body.get("status", {}).get("message", "Disbursement failed"),
            )

        except httpx.HTTPError as exc:
            logger.error("Airtel disburse error txn=%s: %s", txn_id, exc)
            self._access_token = None
            return AirtelPaymentResult(
                success=False,
                provider_reference=txn_id,
                status="TF",
                response_code="HTTP_ERROR",
                raw_response={},
                error_message=str(exc),
            )


class AirtelMoneyError(Exception):
    """Raised for unrecoverable Airtel Money API errors."""
