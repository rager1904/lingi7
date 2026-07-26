"""
Generic carrier client base and factory.

All carrier clients implement a common interface. The factory returns
the correct client for a given CarrierCode. Carrier-specific clients
live in their own modules.

Reference: LG7-BE-009 | apps/logistics/carriers/generic.py
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class BaseCarrierClient(ABC):
    """
    Abstract base for all carrier API clients.

    Every carrier client must implement get_tracking_status().
    The return dict uses normalised status values from Shipment.Status.
    """

    @abstractmethod
    def get_tracking_status(self, tracking_number: str) -> dict | None:
        """
        Fetch the latest tracking status for a given tracking number.

        Args:
            tracking_number: Carrier-assigned tracking reference.

        Returns:
            Dict with keys: status, description, location, event_timestamp, raw.
            None if no update is available or tracking number not found.
        """
        raise NotImplementedError


class GenericCarrierClient:
    """
    Factory that returns the appropriate carrier client.

    Usage:
        client = GenericCarrierClient.get_client(shipment.carrier)
        if client:
            result = client.get_tracking_status(tracking_number)
    """

    @staticmethod
    def get_client(carrier_code: str) -> BaseCarrierClient | None:
        """
        Return the carrier client for the given CarrierCode.

        Args:
            carrier_code: Value from Shipment.CarrierCode.

        Returns:
            A BaseCarrierClient subclass instance, or None if no
            API integration exists for this carrier.
        """
        from apps.logistics.models import Shipment

        clients = {
            Shipment.CarrierCode.DHL: DHLZambiaClient,
            # Shipment.CarrierCode.FEDEX: FedExClient,  # Phase 3
            # Shipment.CarrierCode.ZAMPOST: ZampostClient,  # Phase 3
        }

        client_class = clients.get(carrier_code)
        if client_class is None:
            logger.debug(
                "No API client registered for carrier '%s'. "
                "Manual tracking only.",
                carrier_code,
            )
            return None

        return client_class()


class DHLZambiaClient(BaseCarrierClient):
    """
    DHL Zambia carrier client.

    Polls DHL's tracking API for shipment status updates.
    In Phase 1, this is a stub — DHL integration is fully implemented
    in Phase 2 (Step 9 — carrier integrations).

    Reference: DHL Express Tracking API v2
    https://developer.dhl.com/api-reference/shipment-tracking
    """

    API_BASE = "https://api-eu.dhl.com/track/shipments"

    def __init__(self) -> None:
        from django.conf import settings
        self.api_key: str = getattr(settings, "DHL_API_KEY", "")

    def get_tracking_status(self, tracking_number: str) -> dict | None:
        """
        Fetch tracking status from DHL API.

        In Phase 1, logs a warning and returns None (manual updates only).
        Full implementation in Phase 2.

        Args:
            tracking_number: DHL waybill number.

        Returns:
            Normalised tracking dict or None.
        """
        if not self.api_key:
            logger.warning(
                "DHL_API_KEY not configured. "
                "DHL tracking is manual-only until Phase 2."
            )
            return None

        # Phase 2: Implement actual DHL API call here.
        # import httpx
        # response = httpx.get(
        #     self.API_BASE,
        #     params={"trackingNumber": tracking_number},
        #     headers={"DHL-API-Key": self.api_key},
        #     timeout=10.0,
        # )
        # response.raise_for_status()
        # return self._normalise(response.json())

        logger.debug("DHLZambiaClient.get_tracking_status — stub for %s", tracking_number)
        return None

    def _normalise(self, raw: dict) -> dict | None:
        """
        Normalise DHL API response to the common tracking dict format.

        Args:
            raw: Raw DHL API response dict.

        Returns:
            Normalised dict with status, description, location,
            event_timestamp, raw keys.
        """
        # Phase 2 implementation
        return None
