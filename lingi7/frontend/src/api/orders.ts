import apiClient from "./client";
import {
  mapApiOrderToDetail,
  mapApiOrderToListItem,
  mapOrderDisputesFromOrders,
  normalizeOrderListResponse,
} from "./orderMappers";
import type { Dispute, Order, OrderListItem, PaginatedResponse } from "../types";

export interface CreateOrderPayload {
  seller_id: string;
  lines: Array<{
    product_id: number;
    quantity: number;
  }>;
  delivery_address: string;
  buyer_notes?: string;
  fulfilment_type?: string;
}

export const ordersApi = {
  list: async (page = 1): Promise<PaginatedResponse<OrderListItem>> => {
    const { data } = await apiClient.get<unknown>("/orders/", { params: { page } });
    const rawList = normalizeOrderListResponse(data);
    const results = rawList.map(mapApiOrderToListItem);
    const paginated =
      data && typeof data === "object" && !Array.isArray(data)
        ? (data as PaginatedResponse<unknown>)
        : null;

    return {
      count: paginated?.count ?? results.length,
      next: paginated?.next ?? null,
      previous: paginated?.previous ?? null,
      results,
    };
  },

  retrieve: async (orderId: string): Promise<Order> => {
    const { data } = await apiClient.get<unknown>(`/orders/${orderId}/`);
    return mapApiOrderToDetail(data as Parameters<typeof mapApiOrderToDetail>[0]);
  },

  create: async (payload: CreateOrderPayload): Promise<Order> => {
    const { data } = await apiClient.post<unknown>("/orders/", payload);
    return mapApiOrderToDetail(data as Parameters<typeof mapApiOrderToDetail>[0]);
  },

  submit: async (orderId: string): Promise<Order> => {
    const { data } = await apiClient.post<unknown>(`/orders/${orderId}/submit/`);
    return mapApiOrderToDetail(data as Parameters<typeof mapApiOrderToDetail>[0]);
  },

  cancel: async (orderId: string, reason = ""): Promise<Order> => {
    const { data } = await apiClient.post<unknown>(`/orders/${orderId}/cancel/`, {
      reason,
    });
    return mapApiOrderToDetail(data as Parameters<typeof mapApiOrderToDetail>[0]);
  },

  confirmDelivery: async (orderId: string): Promise<Order> => {
    const { data } = await apiClient.post<unknown>(
      `/orders/${orderId}/confirm-delivery/`
    );
    return mapApiOrderToDetail(data as Parameters<typeof mapApiOrderToDetail>[0]);
  },

  raiseDispute: async (
    orderId: string,
    reason: string,
    description: string,
    evidence_urls: string[] = []
  ): Promise<unknown> => {
    const { data } = await apiClient.post(`/orders/${orderId}/dispute/`, {
      reason,
      description,
      evidence_urls,
    });
    return data;
  },

  acknowledge: async (orderId: string): Promise<Order> => {
    const { data } = await apiClient.post<unknown>(`/orders/${orderId}/acknowledge/`);
    return mapApiOrderToDetail(data as Parameters<typeof mapApiOrderToDetail>[0]);
  },

  ship: async (
    orderId: string,
    payload: {
      carrier: string;
      tracking_number?: string;
      tracking_url?: string;
      notes?: string;
    }
  ): Promise<Order> => {
    const { data } = await apiClient.post<unknown>(`/orders/${orderId}/ship/`, payload);
    return mapApiOrderToDetail(data as Parameters<typeof mapApiOrderToDetail>[0]);
  },

  /** Orders where the authenticated user is seller (client-side filter). */
  listAsSeller: async (page = 1): Promise<OrderListItem[]> => {
    const { data } = await apiClient.get<unknown>("/orders/", {
      params: { page, role: "seller" },
    });
    const rawList = normalizeOrderListResponse(data);
    return rawList.map(mapApiOrderToListItem);
  },

  /** Order disputes raised via POST /orders/{id}/dispute/ (orders app). */
  listDisputes: async (): Promise<Dispute[]> => {
    const { data } = await apiClient.get<unknown>("/orders/");
    const rawList = normalizeOrderListResponse(data);
    return mapOrderDisputesFromOrders(rawList);
  },
};
