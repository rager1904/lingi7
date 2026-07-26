/**
 * Lingi7 Utility Functions
 */

import type { EscrowStatus, ShipmentStatus } from "../types";

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

export const ORDER_STATUS_LABEL: Record<string, string> = {
  DRAFT: "Draft",
  PENDING_PAYMENT: "Awaiting Payment",
  PAYMENT_RECEIVED: "Payment Received",
  PROCESSING: "Processing",
  SHIPPED: "Shipped",
  DELIVERED: "Delivered",
  COMPLETED: "Completed",
  DISPUTED: "Disputed",
  CANCELLED: "Cancelled",
  REFUNDED: "Refunded",
  PLACED: "Order Placed",
  CONFIRMED: "Confirmed",
};

export function getOrderStatusLabel(status: string): string {
  return ORDER_STATUS_LABEL[status] ?? status.replace(/_/g, " ");
}

export const FULFILMENT_TYPE_LABEL: Record<string, string> = {
  STANDARD_DELIVERY: "Standard delivery",
  PICKUP: "Pickup from seller",
  DIGITAL: "Digital delivery",
};

export const ZAMBIA_PROVINCES = [
  "Copperbelt",
  "Lusaka",
  "Central",
  "Eastern",
  "Luapula",
  "Muchinga",
  "Northern",
  "North-Western",
  "Southern",
  "Western",
] as const;

/** NRC format: XXXXXX/YY/Z (e.g. 123456/78/1) */
export function isValidNrcNumber(nrc: string): boolean {
  return /^\d{6}\/\d{2}\/[1-9]$/.test(nrc.trim());
}

export const SHIPMENT_STATUS_LABEL: Record<ShipmentStatus, string> = {
  CREATED: "Shipment Created",
  DISPATCHED: "Dispatched",
  IN_TRANSIT: "In Transit",
  CUSTOMS: "Customs Clearance",
  CLEARED: "Cleared",
  DELIVERED: "Delivered",
};

// ─── Phone number (Zambia mobile) ─────────────────────────────────────────────

/** MTN 96/76/56, Airtel 97/77/57, Zamtel 95/75/55 — 9 digits after +260 */
const ZM_E164_REGEX = /^\+260(9[5-7]|7[5-7]|5[5-7])\d{7}$/;

/**
 * Normalise to E.164 (+260XXXXXXXXX).
 * Accepts 097…, 077…, 056…, bare 9-digit, or full +260…
 */
export function normalizeZambianPhone(input: string): string {
  if (!input) return "+260";

  const s = input.trim().replace(/[\s-]/g, "");

  if (s.startsWith("+")) return s;
  if (s.startsWith("260") && s.length >= 12) return `+${s}`;
  if (s.startsWith("0") && s.length >= 10) return `+260${s.slice(1)}`;

  const digits = s.replace(/\D/g, "");
  if (digits.length === 9) return `+260${digits}`;
  if (digits.length === 12 && digits.startsWith("260")) return `+${digits}`;
  if (digits) return `+260${digits.replace(/^260/, "")}`;

  return s;
}

export function isValidZambianPhone(phone: string): boolean {
  return ZM_E164_REGEX.test(normalizeZambianPhone(phone));
}

/** Local part only (9 digits) for PhoneInput display */
export function splitZambianPhoneLocal(e164: string): string {
  const n = normalizeZambianPhone(e164);
  return n.startsWith("+260") ? n.slice(4) : "";
}

/** Format phone for display: +260971234567 → +260 97 123 4567 */
export function formatPhone(phone: string): string {
  const n = normalizeZambianPhone(phone);
  if (!n.startsWith("+260") || n.length < 13) return phone;
  return n.replace(/(\+260)(\d{2})(\d{3})(\d{4})/, "$1 $2 $3 $4");
}

// ─── API error extraction ─────────────────────────────────────────────────────

function flattenFieldErrors(
  detail: unknown,
  prefix = ""
): Record<string, string> {
  if (!detail || typeof detail !== "object" || Array.isArray(detail)) {
    return {};
  }
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(detail)) {
    const field = prefix ? `${prefix}.${key}` : key;
    if (Array.isArray(value)) {
      out[field] = String(value[0]);
    } else if (typeof value === "string") {
      out[field] = value;
    } else if (value && typeof value === "object") {
      Object.assign(out, flattenFieldErrors(value, field));
    }
  }
  return out;
}

export function extractFieldErrors(error: unknown): Record<string, string> {
  if (!error || typeof error !== "object") return {};
  const e = error as {
    fields?: Record<string, string | string[]>;
    message?: string;
  };
  if (e.fields && Object.keys(e.fields).length) {
    return Object.fromEntries(
      Object.entries(e.fields).map(([k, v]) => [
        k,
        Array.isArray(v) ? v[0] : String(v),
      ])
    );
  }
  // Lingi7 envelope nests validation errors under error.detail
  const nested = (error as { response?: { data?: { error?: { detail?: unknown } } } })
    .response?.data?.error?.detail;
  if (nested) return flattenFieldErrors(nested);
  return {};
}

export function extractMessage(error: unknown): string {
  if (!error || typeof error !== "object") return "An unexpected error occurred.";
  const e = error as { message?: string };
  if (e.message && e.message !== "An error occurred. Please try again.") {
    return e.message;
  }
  const fields = extractFieldErrors(error);
  const first = Object.values(fields)[0];
  if (first) return first;
  return e.message || "An unexpected error occurred.";
}
