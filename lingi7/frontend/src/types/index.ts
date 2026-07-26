/**
 * Lingi7 TypeScript Type Definitions
 * Mirrors Django DRF serializer shapes exactly.
 * Keep in sync with backend serializers on every API change.
 */

// ─── Auth & Users ────────────────────────────────────────────────────────────

export type UserRole = "BUYER" | "VENDOR" | "ADMIN" | "SUPPORT";
export type KYCStatus =
  | "UNVERIFIED"
  | "PENDING"
  | "VERIFIED"
  | "REJECTED";

export interface User {
  id: string;
  phone_number: string;
  full_name: string;
  email: string | null;
  role: UserRole;
  kyc_status: KYCStatus;
  is_active: boolean;
  is_frozen?: boolean;
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
  email?: string;
  password: string;
  password_confirm: string;
  role: "BUYER" | "VENDOR";
  consent_given: boolean;
  nrc_number?: string;
}

export type FulfilmentType = "STANDARD_DELIVERY" | "PICKUP" | "DIGITAL";

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
  in_stock: boolean;
  category: Category;
  store_name: string;
  store_slug: string;
  seller_id?: string;
  images: ProductImage[];
  status: ProductStatus;
  created_at: string;
  features?: string[];
  specs?: Record<string, string>;
  tags?: string[];
  descriptions_i18n?: Record<string, string>;
  meta_title?: string;
  meta_description?: string;
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
  in_stock: boolean;
  seller_id?: string;
}

export interface PublicStore {
  name: string;
  slug: string;
  description: string;
  logo: string | null;
  banner: string | null;
  product_count: number;
}

// ─── Orders ──────────────────────────────────────────────────────────────────

export type OrderStatus =
  | "DRAFT"
  | "PENDING_PAYMENT"
  | "PAYMENT_RECEIVED"
  | "PROCESSING"
  | "SHIPPED"
  | "DELIVERED"
  | "COMPLETED"
  | "DISPUTED"
  | "CANCELLED"
  | "REFUNDED"
  // Legacy aliases used in older UI copy
  | "PLACED"
  | "CONFIRMED";

export interface OrderItem {
  id: string;
  product_id: number;
  product_name: string;
  product_image_url: string | null;
  quantity: number;
  unit_price_zmw: string;
  line_total_zmw: string;
}

/** Embedded on OrderSerializer from the orders app (not logistics API). */
export interface OrderShipment {
  id: number;
  carrier: string;
  tracking_number: string | null;
  tracking_url: string | null;
  estimated_delivery: string | null;
  shipped_at: string | null;
  notes?: string;
}

export interface Order {
  id: string;
  reference: string;
  status: OrderStatus;
  items: OrderItem[];
  subtotal_zmw: string;
  platform_fee_zmw: string;
  delivery_fee_zmw: string;
  total_zmw: string;
  delivery_address: string;
  fulfilment_type?: FulfilmentType;
  buyer_notes?: string;
  escrow_status: EscrowStatus;
  escrow_id: string;
  payment_provider: "MTN" | "AIRTEL" | null;
  shipment?: OrderShipment | null;
  created_at: string;
  updated_at: string;
}

export interface OrderListItem {
  id: string;
  reference: string;
  status: OrderStatus;
  total_zmw: string;
  item_count: number;
  escrow_status: EscrowStatus;
  created_at: string;
}

/** @deprecated Use CreateOrderPayload from api/orders */
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
  id: string;
  provider: PaymentProvider | string;
  status: PaymentStatus;
  amount_zmw?: string;
  external_reference: string | null;
  created_at: string;
}

export interface InitiatePaymentPayload {
  order_id: string;
  provider: PaymentProvider;
  phone_number: string;
}

export interface PaymentInitiateResponse {
  payment_id: string;
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
  status_display?: string;
  shipping_method?: string;
  shipping_method_display?: string;
  origin_country?: string;
  destination_country?: string;
  events: TrackingEvent[];
  estimated_delivery: string | null;
  delivered_at?: string | null;
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
  id: string;
  order_reference: string;
  status: DisputeStatus | string;
  reason: string;
  description?: string;
  created_at: string;
}

// ─── Recommendations ─────────────────────────────────────────────────────────

export interface WishlistItem {
  id: number;
  name: string;
  product: number;
  product_detail: ProductListItem;
  note: string;
  created_at: string;
}

export interface RecommendationSection {
  title: string;
  subtitle: string;
  strategy: string;
  products: ProductListItem[];
}

export interface EngagementStats {
  total_likes: number;
  total_views: number;
  total_ratings: number;
  total_wishlist_items: number;
  avg_rating_given: number | null;
  top_categories: string[];
  engagement_score: number;
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
