"""
apps/escrow/tests/test_models.py

Unit tests for EscrowAccount and LedgerEntry model behaviour.
Tests DB-level constraints, the is_terminal property, and the
immutability guards on LedgerEntry.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.escrow.models import EscrowAccount, LedgerEntry
from apps.escrow.state_machine import EscrowState

pytestmark = pytest.mark.django_db


class TestEscrowAccountModel:

    def test_default_state_is_pending(self, order_ref, buyer_ref) -> None:
        account = EscrowAccount.objects.create(
            order_ref=order_ref,
            buyer_ref=buyer_ref,
            balance=Decimal("0.00"),
        )
        assert account.state == EscrowState.PENDING

    def test_default_currency_is_zmw(self, order_ref, buyer_ref) -> None:
        account = EscrowAccount.objects.create(
            order_ref=order_ref,
            buyer_ref=buyer_ref,
            balance=Decimal("0.00"),
        )
        assert account.currency == "ZMW"

    def test_order_ref_is_unique(self, order_ref, buyer_ref) -> None:
        from django.db import IntegrityError
        EscrowAccount.objects.create(order_ref=order_ref, buyer_ref=buyer_ref, balance=Decimal("0.00"))
        with pytest.raises(IntegrityError):
            EscrowAccount.objects.create(order_ref=order_ref, buyer_ref=buyer_ref, balance=Decimal("0.00"))

    def test_is_terminal_false_for_held(self, held_account) -> None:
        assert held_account.is_terminal is False

    def test_is_terminal_true_for_released(self, delivered_account) -> None:
        from apps.escrow.services import EscrowService
        released = EscrowService.release_funds(account_id=delivered_account.id)
        assert released.is_terminal is True

    def test_str_repr(self, pending_account) -> None:
        s = str(pending_account)
        assert "EscrowAccount" in s
        assert "PENDING" in s


class TestLedgerEntryModel:

    def test_uuid_primary_key(self, held_account) -> None:
        entry = LedgerEntry.objects.filter(account=held_account).first()
        assert isinstance(entry.id, uuid.UUID)

    def test_immutability_guard_on_save(self, held_account) -> None:
        entry = LedgerEntry.objects.filter(account=held_account).first()
        entry._is_new = False
        with pytest.raises(RuntimeError, match="immutable"):
            entry.save()

    def test_immutability_guard_on_delete(self, held_account) -> None:
        entry = LedgerEntry.objects.filter(account=held_account).first()
        with pytest.raises(RuntimeError, match="cannot be deleted"):
            entry.delete()

    def test_operation_ref_groups_pair(self, held_account) -> None:
        entries = LedgerEntry.objects.filter(account=held_account)
        op_refs = set(entries.values_list("operation_ref", flat=True))
        assert len(op_refs) == 1

    def test_str_repr(self, held_account) -> None:
        entry = LedgerEntry.objects.filter(account=held_account).first()
        s = str(entry)
        assert "LedgerEntry" in s
        assert entry.entry_type in s
