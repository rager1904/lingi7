/**
 * Lingi7 Utility Functions
 */

import type { EscrowStatus, OrderStatus, ShipmentStatus } from "../types";

// ─── Currency ─────────────────────────────────────────────────────────────────

/**
 * Format a decimal string or number as Zambian Kwacha.
 * e.g. "1250.00" → "K 1,250.00"
 */
export function formatZMW(value: string | number): string {
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "K 0.00";
  return `K ${num.toLocaleString("en-ZM", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

// ─── Dates ────────────────────────────────────────────────────────────────────

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-ZM", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-ZM", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// ─── Status Labels & Colours ─────────────────────────────────────────────────

export const ESCROW_STATUS_LABEL: Record<EscrowStatus, string> = {
  PENDING: "Awaiting Payment",
  HELD: "Payment Secured",
  IN_TRANSIT: "In Transit",
  DELIVERED: "Delivered",
  RELEASED: "Completed",
  DISPUTED: "Dispute Open",
  REFUNDED: "Refunded",
  FROZEN: "Under Review",
};

export const ESCROW_STATUS_COLOUR: Record<
  EscrowStatus,
  "gray" | "yellow" | "blue" | "green" | "red" | "orange"
> = {
  PENDING: "gray",
  HELD: "yellow",
  IN_TRANSIT: "blue",
  DELIVERED: "blue",
  RELEASED: "green",
  DISPUTED: "red",
  REFUNDED: "orange",
  FROZEN: "orange",
};

export const ORDER_STATUS_LABEL: Record<OrderStatus, string> = {
  PLACED: "Order Placed",
  CONFIRMED: "Confirmed",
  SHIPPED: "Shipped",
  DELIVERED: "Delivered",
  CANCELLED: "Cancelled",
};

export const SHIPMENT_STATUS_LABEL: Record<ShipmentStatus, string> = {
  CREATED: "Shipment Created",
  DISPATCHED: "Dispatched",
  IN_TRANSIT: "In Transit",
  CUSTOMS: "Customs Clearance",
  CLEARED: "Cleared",
  DELIVERED: "Delivered",
};

// ─── Phone number ─────────────────────────────────────────────────────────────

/** Validate Zambian phone number format (+260XXXXXXXXX) */
export function isValidZambianPhone(phone: string): boolean {
  return /^\+2609[5-7]\d{7}$/.test(phone);
}

/** Format phone for display: +260971234567 → +260 97 123 4567 */
export function formatPhone(phone: string): string {
  if (!phone.startsWith("+260")) return phone;
  return phone.replace(/(\+260)(\d{2})(\d{3})(\d{4})/, "$1 $2 $3 $4");
}

// ─── API error extraction ─────────────────────────────────────────────────────

export function extractFieldErrors(
  error: unknown
): Record<string, string> {
  if (!error || typeof error !== "object") return {};
  const e = error as { fields?: Record<string, string | string[]> };
  if (!e.fields) return {};

  return Object.fromEntries(
    Object.entries(e.fields).map(([k, v]) => [
      k,
      Array.isArray(v) ? v[0] : String(v),
    ])
  );
}

export function extractMessage(error: unknown): string {
  if (!error || typeof error !== "object") return "An unexpected error occurred.";
  const e = error as { message?: string };
  return e.message || "An unexpected error occurred.";
}
