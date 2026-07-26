"""
apps/escrow/tests/conftest.py

Shared pytest fixtures for the escrow test suite.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.escrow.models import EscrowAccount, EscrowHold, LedgerEntry, ReconciliationLog
from apps.escrow.services import EscrowService
from apps.escrow.state_machine import EscrowState


@pytest.fixture(autouse=True)
def clean_db():
    """Clean the database before each test to ensure isolation."""
    ReconciliationLog.objects.all().delete()
    LedgerEntry.objects.all().delete()
    EscrowHold.objects.all().delete()
    EscrowAccount.objects.all().delete()


@pytest.fixture
def order_ref() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def buyer_ref() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def vendor_ref() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def pending_account(order_ref, buyer_ref, vendor_ref) -> EscrowAccount:
    """A freshly created EscrowAccount in PENDING state."""
    return EscrowService.create_account(
        order_ref=order_ref,
        buyer_ref=buyer_ref,
        vendor_ref=vendor_ref,
    )


@pytest.fixture
def held_account(pending_account) -> EscrowAccount:
    """EscrowAccount that has been funded (HELD state, ZMW 1000)."""
    return EscrowService.hold_funds(
        account_id=pending_account.id,
        amount=Decimal("1000.00"),
        payment_provider="MTN",
        collection_ref="MTN-TEST-001",
    )


@pytest.fixture
def in_transit_account(held_account) -> EscrowAccount:
    return EscrowService.mark_in_transit(account_id=held_account.id)


@pytest.fixture
def delivered_account(in_transit_account) -> EscrowAccount:
    return EscrowService.mark_delivered(account_id=in_transit_account.id)
