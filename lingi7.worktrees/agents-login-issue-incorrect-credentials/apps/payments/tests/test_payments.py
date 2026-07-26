"""
apps/payments/tests/test_payments.py

Test suite for the payments app.
Covers: models, MTN MoMo client, Airtel client, idempotency,
        webhook receivers, and PaymentService.

Run: docker compose exec web /opt/venv/bin/pytest apps/payments/tests/ -v --tb=short

Doc Ref: LG7-BE-005 v1.0
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.core.cache import cache

User = get_user_model()


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #

@pytest.fixture(autouse=True)
def clear_cache():
    """Clear Redis cache between tests to reset idempotency state."""
    yield
    cache.clear()


@pytest.fixture
def vendor_user(db):
    return User.objects.create_user(
        phone_number="+260971000001",
        password="testpass123",
        role="VENDOR",
    )


@pytest.fixture
def buyer_user(db):
    return User.objects.create_user(
        phone_number="+260971000002",
        password="testpass123",
        role="BUYER",
    )


@pytest.fixture
def escrow_account_id():
    return uuid.uuid4()


@pytest.fixture
def order_id():
    return uuid.uuid4()


# ------------------------------------------------------------------ #
# Model tests                                                         #
# ------------------------------------------------------------------ #

class TestPaymentAttemptModel(TestCase):
    """Tests for PaymentAttempt model."""

    def _make_attempt(self, **kwargs) -> "PaymentAttempt":
        from apps.payments.models import PaymentAttempt
        defaults = {
            "idempotency_key": f"COLLECT-{uuid.uuid4()}-1",
            "order_id": uuid.uuid4(),
            "escrow_account_id": uuid.uuid4(),
            "provider": "MTN_MOMO",
            "direction": PaymentAttempt.Direction.COLLECTION,
            "amount": Decimal("500.00"),
            "payer_phone": "260971234567",
            "status": PaymentAttempt.Status.INITIATED,
            "attempt_number": 1,
        }
        defaults.update(kwargs)
        return PaymentAttempt.objects.create(**defaults)

    def test_create_attempt_succeeds(self):
        attempt = self._make_attempt()
        self.assertIsNotNone(attempt.pk)
        self.assertEqual(attempt.status, "INITIATED")

    def test_is_terminal_for_success(self):
        from apps.payments.models import PaymentAttempt
        attempt = self._make_attempt(status=PaymentAttempt.Status.SUCCESS)
        self.assertTrue(attempt.is_terminal)

    def test_is_terminal_for_failed(self):
        from apps.payments.models import PaymentAttempt
        attempt = self._make_attempt(status=PaymentAttempt.Status.FAILED)
        self.assertTrue(attempt.is_terminal)

    def test_is_not_terminal_for_pending(self):
        from apps.payments.models import PaymentAttempt
        attempt = self._make_attempt(status=PaymentAttempt.Status.PENDING)
        self.assertFalse(attempt.is_terminal)

    def test_idempotency_key_unique_constraint(self):
        from apps.payments.models import PaymentAttempt
        from django.db import IntegrityError
        key = "COLLECT-unique-key-001"
        self._make_attempt(idempotency_key=key)
        with self.assertRaises(IntegrityError):
            self._make_attempt(idempotency_key=key)


class TestWebhookEventModel(TestCase):
    """Tests for WebhookEvent model."""

    def _make_webhook(self, **kwargs) -> "WebhookEvent":
        from apps.payments.models import WebhookEvent
        defaults = {
            "provider": "MTN_MOMO",
            "provider_reference": str(uuid.uuid4()),
            "event_type": "SUCCESSFUL",
            "payload": {"status": "SUCCESSFUL"},
            "headers": {},
            "signature_valid": True,
        }
        defaults.update(kwargs)
        return WebhookEvent.objects.create(**defaults)

    def test_mark_processed(self):
        from apps.payments.models import WebhookEvent
        wh = self._make_webhook()
        wh.mark_processed()
        wh.refresh_from_db()
        self.assertEqual(wh.status, WebhookEvent.Status.PROCESSED)
        self.assertIsNotNone(wh.processed_at)

    def test_mark_duplicate(self):
        from apps.payments.models import WebhookEvent
        wh = self._make_webhook()
        wh.mark_duplicate()
        wh.refresh_from_db()
        self.assertEqual(wh.status, WebhookEvent.Status.DUPLICATE)

    def test_mark_error(self):
        from apps.payments.models import WebhookEvent
        wh = self._make_webhook()
        wh.mark_error("Connection refused")
        wh.refresh_from_db()
        self.assertEqual(wh.status, WebhookEvent.Status.ERROR)
        self.assertIn("Connection refused", wh.processing_error)

    def test_provider_reference_unique_per_provider(self):
        """Same reference from same provider must be rejected at DB level."""
        from django.db import IntegrityError
        ref = "UNIQUE-REF-001"
        self._make_webhook(provider="MTN_MOMO", provider_reference=ref)
        with self.assertRaises(IntegrityError):
            self._make_webhook(provider="MTN_MOMO", provider_reference=ref)

    def test_same_reference_different_provider_allowed(self):
        """Same reference from different providers is allowed."""
        ref = "SHARED-REF-001"
        wh1 = self._make_webhook(provider="MTN_MOMO", provider_reference=ref)
        wh2 = self._make_webhook(provider="AIRTEL", provider_reference=ref)
        self.assertNotEqual(wh1.pk, wh2.pk)


# ------------------------------------------------------------------ #
# MTN MoMo client tests                                               #
# ------------------------------------------------------------------ #

class TestMTNMoMoClient(TestCase):
    """Tests for MTNMoMoClient."""

    def _make_client(self):
        from apps.payments.providers.mtn_momo import MTNMoMoClient, MTNEnvironment
        return MTNMoMoClient(
            collection_api_key="test-col-key",
            collection_user_id="test-col-user",
            disbursement_api_key="test-dis-key",
            disbursement_user_id="test-dis-user",
            subscription_key="test-sub-key",
            environment=MTNEnvironment.SANDBOX,
        )

    @patch("apps.payments.providers.mtn_momo.httpx.Client")
    def test_request_to_pay_success_returns_pending(self, mock_client_cls):
        """requesttopay returning 202 should yield PENDING status."""
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_client_cls.return_value.__enter__.return_value.post.return_value = mock_resp

        client = self._make_client()
        client._collection_token = "fake-token"  # Skip token fetch

        result = client.request_to_pay(
            amount=Decimal("500.00"),
            payer_msisdn="260971234567",
            reference="ORDER-001",
            message="Test payment",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.status, "PENDING")

    @patch("apps.payments.providers.mtn_momo.httpx.Client")
    def test_request_to_pay_failure_returns_failed(self, mock_client_cls):
        """Non-202 response should yield FAILED status."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"code": "PAYER_NOT_FOUND", "message": "Payer not found"}
        mock_client_cls.return_value.__enter__.return_value.post.return_value = mock_resp

        client = self._make_client()
        client._collection_token = "fake-token"

        result = client.request_to_pay(
            amount=Decimal("500.00"),
            payer_msisdn="260000000000",
            reference="ORDER-002",
            message="Test payment",
        )

        self.assertFalse(result.success)
        self.assertEqual(result.status, "FAILED")
        self.assertIn("Payer not found", result.error_message)

    @patch("apps.payments.providers.mtn_momo.httpx.Client")
    def test_request_to_pay_timeout_clears_token(self, mock_client_cls):
        """Timeout should clear cached token and return TIMEOUT status."""
        import httpx
        mock_client_cls.return_value.__enter__.return_value.post.side_effect = (
            httpx.TimeoutException("Connection timed out")
        )

        client = self._make_client()
        client._collection_token = "will-be-cleared"

        result = client.request_to_pay(
            amount=Decimal("100.00"),
            payer_msisdn="260971234567",
            reference="ORDER-003",
            message="Test",
        )

        self.assertFalse(result.success)
        self.assertEqual(result.status, "TIMEOUT")
        self.assertIsNone(client._collection_token)  # Token should be cleared

    @patch("apps.payments.providers.mtn_momo.httpx.Client")
    def test_get_payment_status_successful(self, mock_client_cls):
        """Status poll returning SUCCESSFUL should yield success=True."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "financialTransactionId": "363440463",
            "externalId": "ORDER-001",
            "amount": "500",
            "currency": "ZMW",
            "status": "SUCCESSFUL",
        }
        mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_resp

        client = self._make_client()
        client._collection_token = "fake-token"

        result = client.get_payment_status("test-ref-id")

        self.assertTrue(result.success)
        self.assertEqual(result.status, "SUCCESSFUL")
        self.assertEqual(result.provider_reference, "363440463")

    @patch("apps.payments.providers.mtn_momo.httpx.Client")
    def test_transfer_accepted_returns_pending(self, mock_client_cls):
        """MTN transfer 202 should return PENDING (not yet confirmed)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_client_cls.return_value.__enter__.return_value.post.return_value = mock_resp

        client = self._make_client()
        client._disbursement_token = "fake-dis-token"

        result = client.transfer(
            amount=Decimal("475.00"),
            payee_msisdn="260971234567",
            reference="PAYOUT-001",
            message="Vendor payout",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.status, "PENDING")


# ------------------------------------------------------------------ #
# Airtel client tests                                                  #
# ------------------------------------------------------------------ #

class TestAirtelMoneyClient(TestCase):
    """Tests for AirtelMoneyClient."""

    def _make_client(self):
        from apps.payments.providers.airtel import AirtelMoneyClient
        return AirtelMoneyClient(
            client_id="test-client-id",
            client_secret="test-secret",
            environment="sandbox",
        )

    @patch("apps.payments.providers.airtel.httpx.Client")
    def test_request_payment_success(self, mock_client_cls):
        """Successful collection request should return TP status."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": {"code": "200", "message": "Success", "result_code": "ESB000010"},
            "data": {
                "transaction": {"id": "LINGI-001", "status": "TP"}
            },
        }
        mock_client_cls.return_value.__enter__.return_value.post.return_value = mock_resp

        client = self._make_client()
        client._access_token = "fake-token"

        result = client.request_payment(
            amount=Decimal("300.00"),
            msisdn="260977654321",
            reference="ORDER-004",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.status, "TP")

    @patch("apps.payments.providers.airtel.httpx.Client")
    def test_disburse_success(self, mock_client_cls):
        """Successful disbursement should return TP status."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": {"code": "200", "message": "Success"},
            "data": {"transaction": {"id": "PAYOUT-001"}},
        }
        mock_client_cls.return_value.__enter__.return_value.post.return_value = mock_resp

        client = self._make_client()
        client._access_token = "fake-token"

        result = client.disburse(
            amount=Decimal("285.00"),
            msisdn="260977654321",
            reference="PAYOUT-001",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.status, "TP")

    @patch("apps.payments.providers.airtel.httpx.Client")
    def test_token_cleared_on_401(self, mock_client_cls):
        """401 response should clear cached token."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"status": {"code": "401", "message": "Unauthorized"}}
        mock_client_cls.return_value.__enter__.return_value.post.return_value = mock_resp

        client = self._make_client()
        client._access_token = "expired-token"

        result = client.request_payment(
            amount=Decimal("100.00"),
            msisdn="260977654321",
            reference="ORDER-005",
        )

        self.assertFalse(result.success)
        self.assertIsNone(client._access_token)


# ------------------------------------------------------------------ #
# Idempotency tests                                                   #
# ------------------------------------------------------------------ #

class TestIdempotency(TestCase):
    """Tests for Redis-backed idempotency layer."""

    def test_not_processed_initially(self):
        from apps.payments.idempotency import is_already_processed
        self.assertFalse(is_already_processed("MTN_MOMO", "NEW-REF-001"))

    def test_mark_and_check_processed(self):
        from apps.payments.idempotency import is_already_processed, mark_as_processed
        mark_as_processed("MTN_MOMO", "REF-MARK-001")
        self.assertTrue(is_already_processed("MTN_MOMO", "REF-MARK-001"))

    def test_different_providers_independent(self):
        from apps.payments.idempotency import is_already_processed, mark_as_processed
        mark_as_processed("MTN_MOMO", "SHARED-REF")
        # Airtel should not be affected
        self.assertFalse(is_already_processed("AIRTEL", "SHARED-REF"))

    def test_webhook_processing_lock_raises_on_duplicate(self):
        from apps.payments.idempotency import (
            mark_as_processed,
            webhook_processing_lock,
            WebhookAlreadyProcessedError,
        )
        mark_as_processed("MTN_MOMO", "ALREADY-DONE")
        with self.assertRaises(WebhookAlreadyProcessedError):
            with webhook_processing_lock("MTN_MOMO", "ALREADY-DONE"):
                pass  # Should never reach here

    def test_lock_released_after_context(self):
        """Lock must be released even if an exception occurs inside the context."""
        from apps.payments.idempotency import webhook_processing_lock
        from django.core.cache import cache

        ref = "LOCK-RELEASE-TEST"
        lock_key = f"payments:webhook:lock:MTN_MOMO:{ref}"

        try:
            with webhook_processing_lock("MTN_MOMO", ref):
                self.assertIsNotNone(cache.get(lock_key))
                raise ValueError("Simulated processing error")
        except ValueError:
            pass

        # Lock must be released after exception
        self.assertIsNone(cache.get(lock_key))


# ------------------------------------------------------------------ #
# Webhook receiver tests                                              #
# ------------------------------------------------------------------ #

class TestWebhookReceivers(TestCase):
    """Tests for MTN and Airtel webhook view receivers."""

    def setUp(self):
        self.factory = RequestFactory()

    def _mtn_payload(self, status: str = "SUCCESSFUL", ref: str = "363440463") -> dict:
        return {
            "financialTransactionId": ref,
            "externalId": "ORDER-001",
            "amount": "500",
            "currency": "ZMW",
            "payer": {"partyIdType": "MSISDN", "partyId": "260971234567"},
            "status": status,
        }

    def _airtel_payload(self, status_code: str = "TS", txn_id: str = "LINGI-001") -> dict:
        return {
            "transaction": {
                "id": txn_id,
                "message": "Airtel Money Payment",
                "status_code": status_code,
                "airtel_money_id": f"CI240101.{txn_id}",
            }
        }

    @patch("apps.payments.webhooks._validate_mtn_signature", return_value=True)
    @patch.object(
        __import__("apps.payments.services", fromlist=["PaymentService"]).PaymentService,
        "process_webhook",
        return_value=MagicMock(status="PROCESSED"),
    )
    def test_mtn_webhook_returns_200(self, mock_service, mock_sig):
        from apps.payments.webhooks import MTNMoMoWebhookView
        payload = self._mtn_payload()
        request = self.factory.post(
            "/api/payments/webhooks/momo/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        response = MTNMoMoWebhookView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    @patch("apps.payments.webhooks._validate_mtn_signature", return_value=True)
    @patch.object(
        __import__("apps.payments.services", fromlist=["PaymentService"]).PaymentService,
        "process_webhook",
        return_value=MagicMock(status="PROCESSED"),
    )
    def test_mtn_webhook_invalid_json_returns_200(self, mock_service, mock_sig):
        """Invalid JSON must still return 200 to prevent MTN retry storms."""
        from apps.payments.webhooks import MTNMoMoWebhookView
        request = self.factory.post(
            "/api/payments/webhooks/momo/",
            data="NOT VALID JSON",
            content_type="application/json",
        )
        response = MTNMoMoWebhookView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    @patch("apps.payments.webhooks._validate_airtel_signature", return_value=True)
    @patch.object(
        __import__("apps.payments.services", fromlist=["PaymentService"]).PaymentService,
        "process_webhook",
        return_value=MagicMock(status="PROCESSED"),
    )
    def test_airtel_webhook_returns_200(self, mock_service, mock_sig):
        from apps.payments.webhooks import AirtelMoneyWebhookView
        payload = self._airtel_payload()
        request = self.factory.post(
            "/api/payments/webhooks/airtel/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        response = AirtelMoneyWebhookView.as_view()(request)
        self.assertEqual(response.status_code, 200)


# ------------------------------------------------------------------ #
# PaymentService integration tests                                    #
# ------------------------------------------------------------------ #

class TestPaymentServiceWebhookProcessing(TestCase):
    """Integration tests for PaymentService.process_webhook()."""

    def _make_attempt(self, provider_reference: str = "REF-001") -> "PaymentAttempt":
        from apps.payments.models import PaymentAttempt
        return PaymentAttempt.objects.create(
            idempotency_key=f"COLLECT-{uuid.uuid4()}-1",
            order_id=uuid.uuid4(),
            escrow_account_id=uuid.uuid4(),
            provider="MTN_MOMO",
            direction=PaymentAttempt.Direction.COLLECTION,
            amount=Decimal("500.00"),
            payer_phone="260971234567",
            status=PaymentAttempt.Status.PENDING,
            provider_reference=provider_reference,
            attempt_number=1,
        )

    @patch("apps.payments.tasks.trigger_escrow_hold_on_payment_success.delay")
    def test_successful_webhook_dispatches_escrow_hold(self, mock_task):
        """SUCCESS webhook must dispatch escrow hold task."""
        from apps.payments.services import PaymentService
        from apps.payments.models import WebhookEvent

        ref = f"SUCCESS-REF-{uuid.uuid4()}"
        self._make_attempt(provider_reference=ref)

        PaymentService.process_webhook(
            provider="MTN_MOMO",
            provider_reference=ref,
            event_type="SUCCESSFUL",
            payload={"status": "SUCCESSFUL", "financialTransactionId": ref},
            headers={},
            signature_valid=True,
        )

        mock_task.assert_called_once()

    def test_duplicate_webhook_marked_as_duplicate(self):
        """Second identical webhook must be marked DUPLICATE, not processed again."""
        from apps.payments.services import PaymentService
        from apps.payments.models import WebhookEvent

        ref = f"DUPE-REF-{uuid.uuid4()}"
        self._make_attempt(provider_reference=ref)

        common_args = dict(
            provider="MTN_MOMO",
            provider_reference=ref,
            event_type="SUCCESSFUL",
            payload={"status": "SUCCESSFUL"},
            headers={},
            signature_valid=True,
        )

        with patch("apps.payments.tasks.trigger_escrow_hold_on_payment_success.delay"):
            PaymentService.process_webhook(**common_args)

        # Fire same webhook again
        result = PaymentService.process_webhook(**common_args)
        self.assertEqual(result.status, WebhookEvent.Status.DUPLICATE)

    def test_invalid_signature_webhook_rejected(self):
        """Webhook with invalid signature must be marked INVALID."""
        from apps.payments.services import PaymentService
        from apps.payments.models import WebhookEvent

        ref = f"INVALID-SIG-{uuid.uuid4()}"

        result = PaymentService.process_webhook(
            provider="MTN_MOMO",
            provider_reference=ref,
            event_type="SUCCESSFUL",
            payload={},
            headers={},
            signature_valid=False,
        )
        self.assertEqual(result.status, WebhookEvent.Status.INVALID)

    def test_failed_webhook_does_not_dispatch_escrow_hold(self):
        """FAILED webhook must NOT dispatch escrow hold task."""
        from apps.payments.services import PaymentService

        ref = f"FAIL-REF-{uuid.uuid4()}"
        self._make_attempt(provider_reference=ref)

        with patch("apps.payments.tasks.trigger_escrow_hold_on_payment_success.delay") as mock_task:
            PaymentService.process_webhook(
                provider="MTN_MOMO",
                provider_reference=ref,
                event_type="FAILED",
                payload={"status": "FAILED"},
                headers={},
                signature_valid=True,
            )
            mock_task.assert_not_called()


class TestPaymentServiceCollectionLimits(TestCase):
    """Tests for max collection attempt enforcement."""

    def test_max_attempts_exceeded_raises(self):
        """Fourth collection attempt on same escrow must be rejected."""
        from apps.payments.models import PaymentAttempt
        from apps.payments.services import PaymentService, MaxAttemptsExceededError

        escrow_id = uuid.uuid4()
        # Create 3 existing attempts
        for i in range(1, 4):
            PaymentAttempt.objects.create(
                idempotency_key=f"COLLECT-{escrow_id}-{i}",
                order_id=uuid.uuid4(),
                escrow_account_id=escrow_id,
                provider="MTN_MOMO",
                direction=PaymentAttempt.Direction.COLLECTION,
                amount=Decimal("500.00"),
                payer_phone="260971234567",
                status=PaymentAttempt.Status.FAILED,
                attempt_number=i,
            )

        with self.assertRaises(MaxAttemptsExceededError):
            PaymentService.initiate_collection(
                order_id=uuid.uuid4(),
                escrow_account_id=escrow_id,
                provider="MTN_MOMO",
                amount=Decimal("500.00"),
                payer_phone="260971234567",
                reference="ORDER-001",
            )
