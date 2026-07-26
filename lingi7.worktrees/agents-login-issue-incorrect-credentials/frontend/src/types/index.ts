/**
 * Lingi7 TypeScript Type Definitions
 * Mirrors Django DRF serializer shapes exactly.
 * Keep in sync with backend serializers on every API change.
 */

// ─── Auth & Users ────────────────────────────────────────────────────────────

export type UserRole = "BUYER" | "VENDOR" | "ADMIN" | "SUPPORT";
export type KYCStatus = "PENDING" | "SUBMITTED" | "VERIFIED" | "REJECTED";

export interface User {
  id: number;
  phone_number: string;
  full_name: string;
  email: string | null;
  role: UserRole;
  kyc_status: KYCStatus;
  is_active: boolean;
  date_joined: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface LoginPayload {
  phone_number: string;
  password: string;
}

export interface RegisterPayload {
  phone_number: string;
  full_name: string;
  password: string;
  password_confirm: string;
  role: "BUYER" | "VENDOR";
  nrc_number?: string;
}

// ─── Products ────────────────────────────────────────────────────────────────

export type ProductStatus = "DRAFT" | "PENDING" | "APPROVED" | "REJECTED" | "ARCHIVED";

export interface Category {
  id: number;
  name: string;
  slug: string;
  parent: number | null;
}

export interface ProductImage {
  id: number;
  image_url: string;
  is_primary: boolean;
  order: number;
}

export interface Product {
  id: number;
  name: string;
  slug: string;
  description: string;
  price_zmw: string;
  stock_quantity: number;
  category: Category;
  store_name: string;
  store_slug: string;
  images: ProductImage[];
  status: ProductStatus;
  created_at: string;
}

export interface ProductListItem {
  id: number;
  name: string;
  slug: string;
  price_zmw: string;
  primary_image_url: string | null;
  category_name: string;
  store_name: string;
  stock_quantity: number;
}

// ─── Orders ──────────────────────────────────────────────────────────────────

export type OrderStatus =
  | "PLACED"
  | "CONFIRMED"
  | "SHIPPED"
  | "DELIVERED"
  | "CANCELLED";

export interface OrderItem {
  id: number;
  product_id: number;
  product_name: string;
  product_image_url: string | null;
  quantity: number;
  unit_price_zmw: string;
  line_total_zmw: string;
}

export interface Order {
  id: number;
  reference: string;
  status: OrderStatus;
  items: OrderItem[];
  subtotal_zmw: string;
  delivery_fee_zmw: string;
  total_zmw: string;
  delivery_address: string;
  escrow_status: EscrowStatus;
  escrow_id: number;
  payment_provider: "MTN" | "AIRTEL" | null;
  created_at: string;
  updated_at: string;
}

export interface OrderListItem {
  id: number;
  reference: string;
  status: OrderStatus;
  total_zmw: string;
  item_count: number;
  escrow_status: EscrowStatus;
  created_at: string;
}

export interface PlaceOrderPayload {
  items: Array<{ product_id: number; quantity: number }>;
  delivery_address: string;
  payment_provider: "MTN" | "AIRTEL";
  phone_number: string;
}

// ─── Escrow ──────────────────────────────────────────────────────────────────

export type EscrowStatus =
  | "PENDING"
  | "HELD"
  | "IN_TRANSIT"
  | "DELIVERED"
  | "RELEASED"
  | "DISPUTED"
  | "REFUNDED"
  | "FROZEN";

export interface EscrowAccount {
  id: number;
  order_reference: string;
  status: EscrowStatus;
  balance_zmw: string;
  created_at: string;
  updated_at: string;
}

// ─── Payments ────────────────────────────────────────────────────────────────

export type PaymentStatus = "PENDING" | "SUCCESS" | "FAILED" | "CANCELLED";
export type PaymentProvider = "MTN" | "AIRTEL";

export interface PaymentAttempt {
  id: number;
  provider: PaymentProvider;
  status: PaymentStatus;
  amount_zmw: string;
  external_reference: string | null;
  created_at: string;
}

export interface InitiatePaymentPayload {
  order_id: number;
  provider: PaymentProvider;
  phone_number: string;
}

export interface PaymentInitiateResponse {
  payment_id: number;
  external_reference: string;
  status: PaymentStatus;
  message: string;
}

// ─── Shipment & Tracking ─────────────────────────────────────────────────────

export type ShipmentStatus =
  | "CREATED"
  | "DISPATCHED"
  | "IN_TRANSIT"
  | "CUSTOMS"
  | "CLEARED"
  | "DELIVERED";

export interface TrackingEvent {
  id: number;
  status: ShipmentStatus;
  description: string;
  location: string | null;
  timestamp: string;
}

export interface Shipment {
  id: number;
  tracking_token: string;
  carrier_name: string;
  tracking_number: string | null;
  status: ShipmentStatus;
  events: TrackingEvent[];
  estimated_delivery: string | null;
  created_at: string;
}

// ─── Disputes ────────────────────────────────────────────────────────────────

export type DisputeStatus =
  | "OPEN"
  | "EVIDENCE_SUBMITTED"
  | "UNDER_REVIEW"
  | "RESOLVED_BUYER"
  | "RESOLVED_VENDOR"
  | "CLOSED";

export interface Dispute {
  id: number;
  order_reference: string;
  status: DisputeStatus;
  reason: string;
  description: string;
  created_at: string;
}

// ─── API Responses ───────────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface APIError {
  detail?: string;
  [field: string]: string | string[] | undefined;
}
