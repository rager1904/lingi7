"""
apps/payments/providers/mock.py

Mock payment provider for development and testing.
Simulates MTN MoMo and Airtel Money payment flows without real API calls.

When PAYMENT_MOCK_MODE=true in settings, all payment attempts will:
1. Log the payment attempt
2. Return a simulated USSD prompt to the user
3. Simulate payment completion after a delay
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MockPaymentResult:
    """Simulated payment result for testing."""

    success: bool
    provider_reference: str  # Simulated provider transaction ID
    status: str  # INITIATED, PENDING, SUCCESS, FAILED
    response_code: str
    raw_response: dict[str, Any]
    error_message: str = ""


class MockPaymentProvider:
    """
    Mock payment provider for development.
    
    Returns simulated responses without making real API calls.
    Useful for testing the payment flow without MTN/Airtel credentials.
    """

    @staticmethod
    def request_to_pay(
        amount: Decimal,
        payer_phone: str,
        reference: str,
        message: str = "",
    ) -> MockPaymentResult:
        """
        Simulate a collection request.
        
        In reality, would send USSD prompt to buyer's phone.
        For testing, returns simulated success with a unique transaction ID.
        
        Args:
            amount: Amount in ZMW.
            payer_phone: Buyer's phone number.
            reference: Order reference for tracking.
            message: Payment description.
            
        Returns:
            MockPaymentResult with simulated response.
        """
        mock_transaction_id = str(uuid.uuid4())[:16].upper()
        
        logger.info(
            "MOCK: Collection request | amount=%.2f | phone=%s | ref=%s",
            amount,
            payer_phone,
            reference,
        )
        
        return MockPaymentResult(
            success=True,
            provider_reference=mock_transaction_id,
            status="INITIATED",
            response_code="0",  # 0 = success in MTN API
            raw_response={
                "financialTransactionId": mock_transaction_id,
                "externalId": reference,
                "amount": str(amount),
                "currency": "ZMW",
                "payer": {"partyIdType": "MSISDN", "partyId": payer_phone},
                "message": message,
                "status": "PENDING",
            },
            error_message="",
        )

    @staticmethod
    def get_collection_status(
        external_id: str,
        provider_reference: str,
    ) -> MockPaymentResult:
        """
        Simulate status polling for a collection.
        
        In reality, would query MTN's API for transaction status.
        For testing, simulates successful payment after a few seconds.
        
        Args:
            external_id: External reference (order ID).
            provider_reference: Provider's transaction ID.
            
        Returns:
            MockPaymentResult with simulated status.
        """
        logger.info(
            "MOCK: Status check | external_id=%s | provider_ref=%s",
            external_id,
            provider_reference,
        )
        
        # In real implementation, you might mark as SUCCESS after N seconds
        # For now, always return PENDING to test webhook flow
        return MockPaymentResult(
            success=True,
            provider_reference=provider_reference,
            status="PENDING",  # Simulating waiting for user confirmation
            response_code="0",
            raw_response={
                "financialTransactionId": provider_reference,
                "externalId": external_id,
                "status": "PENDING",
            },
            error_message="",
        )

    @staticmethod
    def request_to_pay_transfer(
        amount: Decimal,
        payee_phone: str,
        reference: str,
        message: str = "",
    ) -> MockPaymentResult:
        """
        Simulate a disbursement (vendor payout).
        
        Args:
            amount: Amount in ZMW.
            payee_phone: Vendor's phone number.
            reference: Payout reference.
            message: Transfer description.
            
        Returns:
            MockPaymentResult with simulated disbursement response.
        """
        mock_transaction_id = str(uuid.uuid4())[:16].upper()
        
        logger.info(
            "MOCK: Disbursement request | amount=%.2f | phone=%s | ref=%s",
            amount,
            payee_phone,
            reference,
        )
        
        return MockPaymentResult(
            success=True,
            provider_reference=mock_transaction_id,
            status="INITIATED",
            response_code="0",
            raw_response={
                "financialTransactionId": mock_transaction_id,
                "externalId": reference,
                "amount": str(amount),
                "currency": "ZMW",
                "payee": {"partyIdType": "MSISDN", "partyId": payee_phone},
                "message": message,
                "status": "PENDING",
            },
            error_message="",
        )

    @staticmethod
    def get_disbursement_status(
        external_id: str,
        provider_reference: str,
    ) -> MockPaymentResult:
        """Simulate status polling for a disbursement."""
        logger.info(
            "MOCK: Disbursement status check | external_id=%s | provider_ref=%s",
            external_id,
            provider_reference,
        )
        
        return MockPaymentResult(
            success=True,
            provider_reference=provider_reference,
            status="PENDING",
            response_code="0",
            raw_response={
                "financialTransactionId": provider_reference,
                "externalId": external_id,
                "status": "PENDING",
            },
            error_message="",
        )
