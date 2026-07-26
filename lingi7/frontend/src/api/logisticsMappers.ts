/**
 * Maps backend logistics tracking payloads to frontend Shipment types.
 */

import type { Shipment, ShipmentStatus, TrackingEvent } from "../types";

interface ApiTrackingEvent {
  status: string;
  description: string;
  location?: string | null;
  event_timestamp: string;
}

interface ApiPublicShipment {
  tracking_token: string;
  carrier: string;
  carrier_tracking_number?: string | null;
  shipping_method?: string;
  shipping_method_display?: string;
  status: string;
  status_display?: string;
  origin_country?: string;
  destination_country?: string;
  estimated_delivery_date?: string | null;
  delivered_at?: string | null;
  events?: ApiTrackingEvent[];
}

const STATUS_MAP: Record<string, ShipmentStatus> = {
  CREATED: "CREATED",
  DISPATCHED: "DISPATCHED",
  IN_TRANSIT: "IN_TRANSIT",
  CUSTOMS: "CUSTOMS",
  CLEARED: "CLEARED",
  OUT_FOR_DELIVERY: "IN_TRANSIT",
  DELIVERED: "DELIVERED",
  FAILED_DELIVERY: "IN_TRANSIT",
  RETURNED: "IN_TRANSIT",
};

export function mapApiShipment(raw: ApiPublicShipment): Shipment {
  const events: TrackingEvent[] = (raw.events ?? []).map((e, idx) => ({
    id: idx + 1,
    status: STATUS_MAP[e.status] ?? "IN_TRANSIT",
    description: e.description || e.status,
    location: e.location ?? null,
    timestamp: e.event_timestamp,
  }));

  return {
    id: 0,
    tracking_token: String(raw.tracking_token),
    carrier_name: raw.carrier,
    tracking_number: raw.carrier_tracking_number ?? null,
    status: STATUS_MAP[raw.status] ?? "CREATED",
    status_display: raw.status_display,
    shipping_method: raw.shipping_method,
    shipping_method_display: raw.shipping_method_display,
    origin_country: raw.origin_country,
    destination_country: raw.destination_country,
    events,
    estimated_delivery: raw.estimated_delivery_date ?? null,
    delivered_at: raw.delivered_at ?? null,
    created_at: events[0]?.timestamp ?? new Date().toISOString(),
  };
}
