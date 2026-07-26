"""
Tests for LogisticsService.

Covers:
- Shipment creation
- Status transitions
- Dispatch (requires tracking number)
- Delivery confirmation + escrow timer dispatch
- Duplicate event handling
- Guard clauses

Reference: LG7-BE-009 | apps/logistics/tests/test_services.py
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.logistics.exceptions import (
    DeliveryAlreadyConfirmedError,
    InvalidShipmentTransitionError,
    ShipmentAlreadyExistsError,
    TrackingNumberRequiredError,
)
from apps.logistics.models import Shipment, TrackingEvent
from apps.logistics.services import LogisticsService


@pytest.fixture
def vendor_user(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(
        phone_number="+260977100001",
        password="pass",
        role="VENDOR",
    )


@pytest.fixture
def buyer_user(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(
        phone_number="+260977100002",
        password="pass",
        role="BUYER",
    )


@pytest.fixture
def admin_user(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(
        phone_number="+260977100003",
        password="pass",
        is_superuser=True,
        is_staff=True,
    )


@pytest.fixture
def mock_order(db, vendor_user, buyer_user):
    """Mock order object — avoids needing full orders app in this test."""
    order = MagicMock()
    order.pk = 1
    order.id = 1
    order.vendor = vendor_user
    order.buyer = buyer_user
    # Ensure no existing shipment
    Shipment.objects.filter(order_id=1).delete()
    return order


@pytest.mark.django_db
class TestCreateShipment:

    def test_creates_shipment_in_created_state(self, mock_order, vendor_user):
        shipment = LogisticsService.create_shipment(
            order=mock_order,
            created_by=vendor_user,
            carrier=Shipment.CarrierCode.GENERIC,
            shipping_method=Shipment.ShippingMethod.AIR,
            origin_address="Guangzhou, China",
            estimated_delivery_date=date(2025, 12, 31),
        )

        assert shipment.status == Shipment.Status.CREATED
        assert shipment.origin_country == "CN"
        assert shipment.destination_country == "ZM"
        assert shipment.estimated_delivery_date == date(2025, 12, 31)

    def test_creates_initial_tracking_event(self, mock_order, vendor_user):
        shipment = LogisticsService.create_shipment(
            order=mock_order,
            created_by=vendor_user,
        )

        events = list(shipment.events.all())
        assert len(events) == 1
        assert events[0].status == Shipment.Status.CREATED
        assert events[0].source == TrackingEvent.Source.VENDOR_MANUAL

    def test_raises_if_order_already_has_shipment(self, mock_order, vendor_user):
        LogisticsService.create_shipment(order=mock_order, created_by=vendor_user)

        with pytest.raises(ShipmentAlreadyExistsError):
            LogisticsService.create_shipment(order=mock_order, created_by=vendor_user)


@pytest.mark.django_db
class TestMarkDispatched:

    @pytest.fixture
    def created_shipment(self, mock_order, vendor_user):
        return LogisticsService.create_shipment(
            order=mock_order, created_by=vendor_user
        )

    def test_dispatches_with_tracking_number(self, created_shipment, vendor_user):
        shipment = LogisticsService.mark_dispatched(
            shipment=created_shipment,
            actor=vendor_user,
            carrier_tracking_number="DHL123456789",
            carrier=Shipment.CarrierCode.DHL,
            location="Guangzhou, China",
        )

        assert shipment.status == Shipment.Status.DISPATCHED
        assert shipment.carrier_tracking_number == "DHL123456789"
        assert shipment.carrier == Shipment.CarrierCode.DHL

    def test_raises_if_no_tracking_number(self, created_shipment, vendor_user):
        with pytest.raises(TrackingNumberRequiredError):
            LogisticsService.mark_dispatched(
                shipment=created_shipment,
                actor=vendor_user,
                carrier_tracking_number="",
            )

    def test_dispatch_creates_tracking_event(self, created_shipment, vendor_user):
        shipment = LogisticsService.mark_dispatched(
            shipment=created_shipment,
            actor=vendor_user,
            carrier_tracking_number="TRACK999",
        )

        dispatched_events = shipment.events.filter(status=Shipment.Status.DISPATCHED)
        assert dispatched_events.count() == 1


@pytest.mark.django_db
class TestTransitionStatus:

    @pytest.fixture
    def dispatched_shipment(self, mock_order, vendor_user):
        s = LogisticsService.create_shipment(order=mock_order, created_by=vendor_user)
        s.carrier_tracking_number = "TRACK001"
        s.save(update_fields=["carrier_tracking_number"])
        return LogisticsService.transition_status(
            shipment=s,
            to_status=Shipment.Status.DISPATCHED,
            actor=vendor_user,
            source=TrackingEvent.Source.VENDOR_MANUAL,
        )

    def test_transitions_through_chain(self, dispatched_shipment, admin_user):
        """Walk the full chain from DISPATCHED to DELIVERED."""
        s = dispatched_shipment

        for to_status in [
            Shipment.Status.IN_TRANSIT,
            Shipment.Status.CUSTOMS,
            Shipment.Status.CLEARED,
            Shipment.Status.OUT_FOR_DELIVERY,
        ]:
            s = LogisticsService.transition_status(
                shipment=s, to_status=to_status, actor=admin_user
            )
            assert s.status == to_status

    def test_raises_on_invalid_transition(self, dispatched_shipment, admin_user):
        with pytest.raises(InvalidShipmentTransitionError):
            LogisticsService.transition_status(
                shipment=dispatched_shipment,
                to_status=Shipment.Status.DELIVERED,
                actor=admin_user,
            )

    def test_requires_tracking_number_for_transit(self, mock_order, vendor_user):
        s = LogisticsService.create_shipment(order=mock_order, created_by=vendor_user)
        # No tracking number set
        with pytest.raises(TrackingNumberRequiredError):
            LogisticsService.transition_status(
                shipment=s,
                to_status=Shipment.Status.DISPATCHED,
                actor=vendor_user,
            )


@pytest.mark.django_db
class TestConfirmDelivery:

    @pytest.fixture
    def out_for_delivery_shipment(self, mock_order, vendor_user, admin_user):
        s = LogisticsService.create_shipment(order=mock_order, created_by=vendor_user)
        s.carrier_tracking_number = "TRACK555"
        s.save(update_fields=["carrier_tracking_number"])

        for to_status in [
            Shipment.Status.DISPATCHED,
            Shipment.Status.IN_TRANSIT,
            Shipment.Status.CUSTOMS,
            Shipment.Status.CLEARED,
            Shipment.Status.OUT_FOR_DELIVERY,
        ]:
            s = LogisticsService.transition_status(
                shipment=s, to_status=to_status, actor=admin_user
            )
        return s

    @patch("apps.logistics.tasks.start_escrow_auto_confirm_timer.apply_async")
    def test_confirm_delivery_sets_delivered_state(
        self, mock_task, out_for_delivery_shipment, buyer_user
    ):
        shipment = LogisticsService.confirm_delivery(
            shipment=out_for_delivery_shipment,
            actor=buyer_user,
            confirmed_by="BUYER",
        )

        assert shipment.status == Shipment.Status.DELIVERED
        assert shipment.delivered_at is not None
        assert shipment.delivery_confirmed_by == "BUYER"

    @patch("apps.logistics.tasks.start_escrow_auto_confirm_timer.apply_async")
    def test_confirm_delivery_dispatches_escrow_task(
        self, mock_task, out_for_delivery_shipment, buyer_user
    ):
        LogisticsService.confirm_delivery(
            shipment=out_for_delivery_shipment,
            actor=buyer_user,
            confirmed_by="BUYER",
        )

        mock_task.assert_called_once()

    @patch("apps.logistics.tasks.start_escrow_auto_confirm_timer.apply_async")
    def test_raises_if_already_delivered(
        self, mock_task, out_for_delivery_shipment, buyer_user
    ):
        LogisticsService.confirm_delivery(
            shipment=out_for_delivery_shipment,
            actor=buyer_user,
            confirmed_by="BUYER",
        )

        # Refresh from DB to pick up delivered state
        out_for_delivery_shipment.refresh_from_db()

        with pytest.raises(DeliveryAlreadyConfirmedError):
            LogisticsService.confirm_delivery(
                shipment=out_for_delivery_shipment,
                actor=buyer_user,
                confirmed_by="BUYER",
            )


@pytest.mark.django_db
class TestIngestTrackingEvent:

    @pytest.fixture
    def in_transit_shipment(self, mock_order, vendor_user, admin_user):
        s = LogisticsService.create_shipment(order=mock_order, created_by=vendor_user)
        s.carrier_tracking_number = "TRACK222"
        s.save(update_fields=["carrier_tracking_number"])
        for to_status in [Shipment.Status.DISPATCHED, Shipment.Status.IN_TRANSIT]:
            s = LogisticsService.transition_status(
                shipment=s, to_status=to_status, actor=admin_user
            )
        return s

    def test_ingests_new_status(self, in_transit_shipment, admin_user):
        shipment = LogisticsService.ingest_tracking_event(
            shipment=in_transit_shipment,
            to_status=Shipment.Status.CUSTOMS,
            description="Arrived at KKIA, Lusaka.",
            location="Kenneth Kaunda Int. Airport",
            actor=admin_user,
        )
        assert shipment.status == Shipment.Status.CUSTOMS

    def test_duplicate_event_does_not_change_status(self, in_transit_shipment, admin_user):
        """Same status arriving twice should be recorded but not cause a re-transition."""
        initial_event_count = in_transit_shipment.events.count()

        LogisticsService.ingest_tracking_event(
            shipment=in_transit_shipment,
            to_status=Shipment.Status.IN_TRANSIT,  # already in this state
            description="Duplicate carrier push.",
            actor=admin_user,
        )

        in_transit_shipment.refresh_from_db()
        assert in_transit_shipment.status == Shipment.Status.IN_TRANSIT
        # Event count increases by 1 (the duplicate is logged)
        assert in_transit_shipment.events.count() == initial_event_count + 1
