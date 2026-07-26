"""
LogisticsService — fat service for all shipment operations.

This is the sole entry point for any code that modifies shipment
or tracking state. Views, tasks, and carrier webhooks all go
through this service — never modify Shipment.status directly.

Reference: LG7-BE-009 | apps/logistics/services.py
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.admin_audit.models import AdminAuditLog
from apps.logistics.exceptions import (
    DeliveryAlreadyConfirmedError,
    InvalidShipmentTransitionError,
    ShipmentAlreadyExistsError,
    TrackingNumberRequiredError,
)
from apps.logistics.models import Shipment, TrackingEvent
from apps.logistics.state_machine import (
    TRACKING_REQUIRED_STATUSES,
    ShipmentStateMachine,
)

logger = logging.getLogger(__name__)


class LogisticsService:
    """
    Handles the full shipment lifecycle for Lingi7.

    All public methods are atomic where they write to both Shipment
    and TrackingEvent. Side effects (Celery tasks, notifications)
    are dispatched after the atomic block completes.
    """

    # ------------------------------------------------------------------ #
    # Shipment creation                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    @transaction.atomic
    def create_shipment(
        order: Any,
        created_by: Any,
        carrier: str = Shipment.CarrierCode.GENERIC,
        shipping_method: str = Shipment.ShippingMethod.AIR,
        carrier_tracking_number: str = "",
        origin_country: str = "CN",
        origin_address: str = "",
        destination_address: str = "",
        freight_forwarder: str = "",
        customs_agent: str = "",
        estimated_delivery_date: Any = None,
        declared_value_usd: Any = None,
        weight_kg: Any = None,
        volume_cbm: Any = None,
        **kwargs: Any,
    ) -> Shipment:
        """
        Create a new Shipment record in CREATED state.

        One order may only have one shipment. Attempting to create a
        second raises ShipmentAlreadyExistsError.

        Args:
            order: The Order instance this shipment belongs to.
            created_by: User (vendor or admin) creating the record.
            carrier: CarrierCode choice.
            shipping_method: ShippingMethod choice.
            carrier_tracking_number: Optional tracking ref at creation time.
            origin_country: ISO country code of dispatch origin (default CN).
            origin_address: Supplier address.
            destination_address: Buyer delivery address.
            freight_forwarder: Company handling the international leg.
            customs_agent: ZRA-licensed clearing agent name.
            estimated_delivery_date: Expected delivery date (date object).
            declared_value_usd: Declared customs value.
            weight_kg: Shipment weight.
            volume_cbm: Shipment volume in cubic metres.

        Returns:
            The newly created Shipment instance.

        Raises:
            ShipmentAlreadyExistsError: If order already has a shipment.
        """
        if Shipment.objects.filter(order=order).exists():
            raise ShipmentAlreadyExistsError(
                f"Order #{order.pk} already has an associated shipment."
            )

        shipment = Shipment.objects.create(
            order=order,
            created_by=created_by,
            carrier=carrier,
            shipping_method=shipping_method,
            carrier_tracking_number=carrier_tracking_number,
            origin_country=origin_country,
            origin_address=origin_address,
            destination_country="ZM",
            destination_address=destination_address,
            freight_forwarder=freight_forwarder,
            customs_agent=customs_agent,
            estimated_delivery_date=estimated_delivery_date,
            declared_value_usd=declared_value_usd,
            weight_kg=weight_kg,
            volume_cbm=volume_cbm,
            status=Shipment.Status.CREATED,
        )

        TrackingEvent.objects.create(
            shipment=shipment,
            status=Shipment.Status.CREATED,
            description="Shipment record created. Awaiting dispatch from origin.",
            source=TrackingEvent.Source.VENDOR_MANUAL,
            location=origin_address[:200] if origin_address else "",
        )

        AdminAuditLog.objects.create(
            actor=created_by,
            action="SHIPMENT_CREATED",
            object_id=shipment.pk,
            before_state="N/A",
            after_state=Shipment.Status.CREATED,
        )

        logger.info(
            "Shipment #%s created for Order #%s by User #%s.",
            shipment.pk,
            order.pk,
            created_by.pk,
        )

        return shipment

    # ------------------------------------------------------------------ #
    # Generic status transition                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    @transaction.atomic
    def transition_status(
        shipment: Shipment,
        to_status: str,
        actor: Any,
        location: str = "",
        description: str = "",
        source: str = TrackingEvent.Source.ADMIN_MANUAL,
        raw_payload: dict | None = None,
        event_timestamp: Any = None,
    ) -> Shipment:
        """
        Transition a shipment to a new status.

        Validates the transition via ShipmentStateMachine, writes a
        TrackingEvent, and logs to AdminAuditLog.

        Args:
            shipment: The Shipment instance to transition.
            to_status: Target status from Shipment.Status.
            actor: User performing the transition.
            location: Physical location description for the tracking event.
            description: Human-readable event description.
            source: TrackingEvent.Source indicating who/what triggered this.
            raw_payload: Optional raw carrier response dict for audit.
            event_timestamp: Carrier-reported timestamp (defaults to now).

        Returns:
            The updated Shipment instance (refreshed from DB).

        Raises:
            InvalidShipmentTransitionError: If transition is not allowed.
            TrackingNumberRequiredError: If tracking number missing for statuses
                that require it.
        """
        # Validate transition
        machine = ShipmentStateMachine(shipment)
        machine.validate_transition(to_status)

        # Guard: some statuses require a carrier tracking number
        if to_status in TRACKING_REQUIRED_STATUSES and not shipment.carrier_tracking_number:
            raise TrackingNumberRequiredError(
                f"A carrier tracking number is required before moving to '{to_status}'."
            )

        from_status = shipment.status

        # Default description if not provided
        if not description:
            description = Shipment.Status(to_status).label

        # Build TrackingEvent
        TrackingEvent.objects.create(
            shipment=shipment,
            status=to_status,
            location=location,
            description=description,
            source=source,
            raw_payload=raw_payload,
            event_timestamp=event_timestamp or timezone.now(),
        )

        # Update Shipment
        update_fields = ["status", "updated_at"]
        shipment.status = to_status

        # Set delivered_at when reaching terminal DELIVERED state
        if to_status == Shipment.Status.DELIVERED and shipment.delivered_at is None:
            shipment.delivered_at = event_timestamp or timezone.now()
            update_fields.append("delivered_at")

        shipment.save(update_fields=update_fields)

        AdminAuditLog.objects.create(
            actor=actor,
            action=f"SHIPMENT_STATUS_{to_status}",
            object_id=shipment.pk,
            before_state=from_status,
            after_state=to_status,
        )

        logger.info(
            "Shipment #%s transitioned %s → %s by User #%s.",
            shipment.pk,
            from_status,
            to_status,
            getattr(actor, "pk", "system"),
        )

        return Shipment.objects.select_related("order").get(pk=shipment.pk)

    # ------------------------------------------------------------------ #
    # Specific high-value transitions                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    @transaction.atomic
    def mark_dispatched(
        shipment: Shipment,
        actor: Any,
        carrier_tracking_number: str,
        carrier: str = "",
        freight_forwarder: str = "",
        location: str = "",
    ) -> Shipment:
        """
        Mark a shipment as dispatched from origin.

        Sets carrier tracking number. This is the first public-facing
        tracking event buyers will see.

        Args:
            shipment: The shipment to dispatch.
            actor: Vendor or admin performing the action.
            carrier_tracking_number: Carrier-assigned waybill/tracking number.
            carrier: Optional CarrierCode override.
            freight_forwarder: Optional freight forwarder company name.
            location: Origin location description.

        Raises:
            TrackingNumberRequiredError: If carrier_tracking_number is empty.
        """
        if not carrier_tracking_number:
            raise TrackingNumberRequiredError(
                "A carrier tracking number is required to mark a shipment as dispatched."
            )

        update_fields = ["carrier_tracking_number", "updated_at"]
        shipment.carrier_tracking_number = carrier_tracking_number

        if carrier:
            shipment.carrier = carrier
            update_fields.append("carrier")

        if freight_forwarder:
            shipment.freight_forwarder = freight_forwarder
            update_fields.append("freight_forwarder")

        shipment.save(update_fields=update_fields)

        return LogisticsService.transition_status(
            shipment=shipment,
            to_status=Shipment.Status.DISPATCHED,
            actor=actor,
            location=location or "Origin — China",
            description=(
                f"Shipment dispatched from origin. "
                f"Tracking: {carrier_tracking_number}."
            ),
            source=TrackingEvent.Source.VENDOR_MANUAL,
        )

    @staticmethod
    @transaction.atomic
    def ingest_tracking_event(
        shipment: Shipment,
        to_status: str,
        description: str,
        location: str = "",
        source: str = TrackingEvent.Source.CARRIER_WEBHOOK,
        raw_payload: dict | None = None,
        event_timestamp: Any = None,
        actor: Any = None,
    ) -> Shipment:
        """
        Ingest a tracking event from a carrier webhook or polling task.

        This is the primary entry point for automated tracking updates.
        If the status hasn't changed (carrier resends same event), the
        event is still recorded but the shipment status is not re-written.

        Args:
            shipment: The shipment to update.
            to_status: New status from carrier.
            description: Carrier-provided event description.
            location: Location string from carrier.
            source: TrackingEvent.Source (webhook vs poll).
            raw_payload: Raw carrier JSON payload for audit trail.
            event_timestamp: Carrier-reported timestamp.
            actor: System user for audit log (optional; uses system account).

        Returns:
            Updated Shipment.
        """
        # Always record the raw event for audit purposes
        if shipment.status == to_status:
            # Status unchanged — record event but skip transition
            TrackingEvent.objects.create(
                shipment=shipment,
                status=to_status,
                location=location,
                description=f"[Duplicate event] {description}",
                source=source,
                raw_payload=raw_payload,
                event_timestamp=event_timestamp or timezone.now(),
            )
            logger.debug(
                "Shipment #%s duplicate event %s — no transition.", shipment.pk, to_status
            )
            return shipment

        # Get the system actor for automated events
        if actor is None:
            actor = LogisticsService._get_system_actor()

        return LogisticsService.transition_status(
            shipment=shipment,
            to_status=to_status,
            actor=actor,
            location=location,
            description=description,
            source=source,
            raw_payload=raw_payload,
            event_timestamp=event_timestamp,
        )

    @staticmethod
    @transaction.atomic
    def confirm_delivery(
        shipment: Shipment,
        actor: Any,
        confirmed_by: str,
        location: str = "Lusaka, Zambia",
    ) -> Shipment:
        """
        Confirm delivery and trigger escrow auto-confirm window.

        This is the most consequential logistics event — it directly
        starts the 7-day escrow auto-confirm countdown. After calling
        this method, the Celery task trigger_escrow_auto_confirm_timer
        is dispatched.

        Args:
            shipment: The shipment being confirmed delivered.
            actor: User confirming delivery (buyer, carrier, admin, system).
            confirmed_by: One of 'BUYER', 'CARRIER', 'AUTO', 'ADMIN'.
            location: Delivery location.

        Returns:
            Updated Shipment with status=DELIVERED.

        Raises:
            DeliveryAlreadyConfirmedError: If already delivered.
            InvalidShipmentTransitionError: If current state doesn't allow
                DELIVERED transition.
        """
        if shipment.is_delivered:
            raise DeliveryAlreadyConfirmedError(
                f"Shipment #{shipment.pk} is already marked as delivered."
            )

        shipment.delivery_confirmed_by = confirmed_by
        shipment.save(update_fields=["delivery_confirmed_by", "updated_at"])

        updated_shipment = LogisticsService.transition_status(
            shipment=shipment,
            to_status=Shipment.Status.DELIVERED,
            actor=actor,
            location=location,
            description=(
                f"Delivery confirmed by {confirmed_by.lower().replace('_', ' ')}. "
                f"Escrow auto-confirm window has started."
            ),
            source=(
                TrackingEvent.Source.SYSTEM
                if confirmed_by == "AUTO"
                else TrackingEvent.Source.CARRIER_WEBHOOK
            ),
        )

        # Dispatch Celery task to start escrow auto-confirm timer
        # This is dispatched AFTER the atomic block completes
        LogisticsService._trigger_escrow_auto_confirm(updated_shipment)

        return updated_shipment

    @staticmethod
    def update_carrier_tracking_number(
        shipment: Shipment,
        carrier_tracking_number: str,
        carrier: str = "",
        actor: Any = None,
    ) -> Shipment:
        """
        Update the carrier tracking number on an existing shipment.

        Used when the vendor initially created the shipment without a
        tracking number and adds it later.

        Args:
            shipment: Shipment to update.
            carrier_tracking_number: New carrier tracking reference.
            carrier: Optional CarrierCode update.
            actor: User making the change.
        """
        if not carrier_tracking_number:
            raise TrackingNumberRequiredError("Tracking number cannot be empty.")

        update_fields = ["carrier_tracking_number", "updated_at"]
        shipment.carrier_tracking_number = carrier_tracking_number

        if carrier:
            shipment.carrier = carrier
            update_fields.append("carrier")

        shipment.save(update_fields=update_fields)

        if actor:
            AdminAuditLog.objects.create(
                actor=actor,
                action="SHIPMENT_TRACKING_UPDATED",
                object_id=shipment.pk,
                before_state=shipment.status,
                after_state=shipment.status,
                notes=f"Tracking number updated to: {carrier_tracking_number}",
            )

        return shipment

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_system_actor() -> Any:
        """
        Return the system user for automated event logging.

        Falls back to first superuser if no dedicated system user exists.
        """
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            return User.objects.filter(is_superuser=True).order_by("pk").first()
        except User.DoesNotExist:
            return None

    @staticmethod
    def _trigger_escrow_auto_confirm(shipment: Shipment) -> None:
        """
        Dispatch Celery task to start the escrow auto-confirm countdown.

        This is called only after a DELIVERED transition. The escrow
        service will auto-release funds after the configured window
        (default 7 days) if the buyer does not raise a dispute.
        """
        from apps.logistics.tasks import start_escrow_auto_confirm_timer

        try:
            order_id = shipment.order_id
            start_escrow_auto_confirm_timer.apply_async(
                args=[order_id],
                countdown=0,  # Immediate dispatch — timer logic is inside the task
            )
            logger.info(
                "Dispatched start_escrow_auto_confirm_timer for Order #%s "
                "(Shipment #%s).",
                order_id,
                shipment.pk,
            )
        except Exception as exc:  # noqa: BLE001
            # Log but do not re-raise — the delivery is confirmed regardless.
            # Celery beat will retry via the reconciliation task.
            logger.error(
                "Failed to dispatch escrow auto-confirm task for Shipment #%s: %s",
                shipment.pk,
                exc,
            )
