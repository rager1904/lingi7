/**
 * Lingi7 API Resource Modules
 * All domain-specific API calls — orders, payments, tracking, products
 */

import apiClient from "./client";
import type {
  Order,
  OrderListItem,
  PlaceOrderPayload,
  PaginatedResponse,
  Dispute,
  InitiatePaymentPayload,
  PaymentInitiateResponse,
  PaymentAttempt,
  Shipment,
  Product,
  ProductListItem,
} from "../types";

// ─── Orders ──────────────────────────────────────────────────────────────────

export const ordersApi = {
  list: async (page = 1): Promise<PaginatedResponse<OrderListItem>> => {
    const { data } = await apiClient.get<PaginatedResponse<OrderListItem>>(
      "/orders/",
      { params: { page } }
    );
    return data;
  },

  retrieve: async (orderId: number): Promise<Order> => {
    const { data } = await apiClient.get<Order>(`/orders/${orderId}/`);
    return data;
  },

  place: async (payload: PlaceOrderPayload): Promise<Order> => {
    const { data } = await apiClient.post<Order>("/orders/", payload);
    return data;
  },

  raiseDispute: async (
    orderId: number,
    reason: string,
    description: string
  ): Promise<Dispute> => {
    const { data } = await apiClient.post<Dispute>(
      `/orders/${orderId}/dispute/`,
      { reason, description }
    );
    return data;
  },
};

// ─── Payments ────────────────────────────────────────────────────────────────

export const paymentsApi = {
  initiate: async (
    payload: InitiatePaymentPayload
  ): Promise<PaymentInitiateResponse> => {
    const { data } = await apiClient.post<PaymentInitiateResponse>(
      "/payments/initiate/",
      payload
    );
    return data;
  },

  pollStatus: async (paymentId: number): Promise<PaymentAttempt> => {
    const { data } = await apiClient.get<PaymentAttempt>(
      `/payments/${paymentId}/status/`
    );
    return data;
  },
};

// ─── Tracking ─────────────────────────────────────────────────────────────────

export const trackingApi = {
  /** Public endpoint — no auth token required */
  byToken: async (token: string): Promise<Shipment> => {
    const { data } = await apiClient.get<Shipment>(`/tracking/${token}/`);
    return data;
  },

  byOrder: async (orderId: number): Promise<Shipment> => {
    const { data } = await apiClient.get<Shipment>(`/orders/${orderId}/shipment/`);
    return data;
  },
};

// ─── Products ────────────────────────────────────────────────────────────────

export const productsApi = {
  list: async (params?: {
    page?: number;
    category?: string;
    search?: string;
    ordering?: string;
  }): Promise<PaginatedResponse<ProductListItem>> => {
    const { data } = await apiClient.get<PaginatedResponse<ProductListItem>>(
      "/products/",
      { params }
    );
    return data;
  },

  retrieve: async (slug: string): Promise<Product> => {
    const { data } = await apiClient.get<Product>(`/products/${slug}/`);
    return data;
  },
};
