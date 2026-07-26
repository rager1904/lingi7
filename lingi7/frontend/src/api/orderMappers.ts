/**
 * Maps backend OrderSerializer payloads to frontend order types.
 */

import type {
  EscrowStatus,
  Order,
  OrderItem,
  OrderListItem,
  OrderShipment,
  OrderStatus,
} from "../types";

interface ApiOrderLine {
  id: string;
  product_id?: string;
  product_name: string;
  unit_price: string | number;
  quantity: number;
  line_total: string | number;
}

interface ApiOrderDispute {
  id: string;
  reason: string;
  description: string;
  is_open?: boolean;
  resolved_at?: string | null;
  created_at: string;
}

export interface ApiOrder {
  id: string;
  reference: string;
  status: string;
  subtotal?: string | number;
  platform_fee?: string | number;
  total_amount?: string | number;
  total_zmw?: string | number;
  delivery_address?: string;
  fulfilment_type?: string;
  buyer_notes?: string;
  created_at: string;
  updated_at?: string;
  lines?: ApiOrderLine[];
  escrow_status?: string;
  item_count?: number;
  shipment?: {
    id: number;
    carrier: string;
    tracking_number?: string | null;
    tracking_url?: string | null;
    estimated_delivery?: string | null;
    shipped_at?: string | null;
    notes?: string;
  } | null;
  disputes?: ApiOrderDispute[];
}

function mapShipment(raw: ApiOrder["shipment"]): OrderShipment | null {
  if (!raw) return null;
  return {
    id: raw.id,
    carrier: raw.carrier,
    tracking_number: raw.tracking_number ?? null,
    tracking_url: raw.tracking_url ?? null,
    estimated_delivery: raw.estimated_delivery ?? null,
    shipped_at: raw.shipped_at ?? null,
    notes: raw.notes,
  };
}

const ORDER_TO_ESCROW: Record<string, EscrowStatus> = {
  DRAFT: "PENDING",
  PENDING_PAYMENT: "PENDING",
  PAYMENT_RECEIVED: "HELD",
  PROCESSING: "HELD",
  SHIPPED: "IN_TRANSIT",
  DELIVERED: "DELIVERED",
  COMPLETED: "RELEASED",
  DISPUTED: "DISPUTED",
  REFUNDED: "REFUNDED",
  CANCELLED: "PENDING",
  // Legacy frontend labels
  PLACED: "PENDING",
  CONFIRMED: "HELD",
};

function toMoney(value: string | number | undefined): string {
  if (value === undefined || value === null) return "0.00";
  return String(value);
}

const KNOWN_ESCROW: EscrowStatus[] = [
  "PENDING", "HELD", "IN_TRANSIT", "DELIVERED", "RELEASED", "DISPUTED", "REFUNDED", "FROZEN",
];

function deriveEscrowStatus(raw: ApiOrder): EscrowStatus {
  const direct = raw.escrow_status as EscrowStatus | undefined;
  if (direct && KNOWN_ESCROW.includes(direct)) {
    return direct;
  }
  return ORDER_TO_ESCROW[raw.status] ?? "PENDING";
}

function mapLine(line: ApiOrderLine): OrderItem {
  const productId = line.product_id ? parseInt(String(line.product_id), 10) : 0;
  return {
    id: String(line.id),
    product_id: Number.isFinite(productId) ? productId : 0,
    product_name: line.product_name,
    product_image_url: null,
    quantity: line.quantity,
    unit_price_zmw: toMoney(line.unit_price),
    line_total_zmw: toMoney(line.line_total),
  };
}

export function mapApiOrderToListItem(raw: ApiOrder): OrderListItem {
  const lines = raw.lines ?? [];
  const itemCount =
    raw.item_count ??
    lines.reduce((sum, line) => sum + (line.quantity ?? 0), 0);

  return {
    id: String(raw.id),
    reference: raw.reference,
    status: raw.status as OrderStatus,
    total_zmw: toMoney(raw.total_zmw ?? raw.total_amount),
    item_count: itemCount,
    escrow_status: deriveEscrowStatus(raw),
    created_at: raw.created_at,
  };
}

export function mapApiOrderToDetail(raw: ApiOrder): Order {
  const lines = raw.lines ?? [];

  return {
    id: String(raw.id),
    reference: raw.reference,
    status: raw.status as OrderStatus,
    items: lines.map(mapLine),
    subtotal_zmw: toMoney(raw.subtotal),
    platform_fee_zmw: toMoney(raw.platform_fee ?? 0),
    delivery_fee_zmw: "0.00",
    total_zmw: toMoney(raw.total_zmw ?? raw.total_amount),
    delivery_address: raw.delivery_address ?? "",
    fulfilment_type: raw.fulfilment_type as Order["fulfilment_type"],
    buyer_notes: raw.buyer_notes ?? "",
    escrow_status: deriveEscrowStatus(raw),
    escrow_id: "",
    payment_provider: null,
    shipment: mapShipment(raw.shipment),
    created_at: raw.created_at,
    updated_at: raw.updated_at ?? raw.created_at,
  };
}

export function normalizeOrderListResponse(
  data: unknown
): ApiOrder[] {
  if (Array.isArray(data)) return data as ApiOrder[];
  if (data && typeof data === "object" && Array.isArray((data as { results?: unknown }).results)) {
    return (data as { results: ApiOrder[] }).results;
  }
  return [];
}

export function mapOrderDisputesFromOrders(rawOrders: ApiOrder[]): import("../types").Dispute[] {
  const rows: import("../types").Dispute[] = [];
  for (const order of rawOrders) {
    for (const dispute of order.disputes ?? []) {
      rows.push({
        id: String(dispute.id),
        order_reference: order.reference,
        status: dispute.is_open === false || dispute.resolved_at ? "CLOSED" : "OPEN",
        reason: dispute.reason.replace(/_/g, " "),
        description: dispute.description,
        created_at: dispute.created_at,
      });
    }
  }
  return rows.sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );
}
