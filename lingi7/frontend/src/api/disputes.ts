import apiClient from "./client";
import type { Dispute } from "../types";

export const disputesApi = {
  list: async (): Promise<Dispute[]> => {
    const { data } = await apiClient.get<unknown>("/disputes/api/disputes/");
    const rows = Array.isArray(data) ? data : [];
    return rows.map((row) => {
      const d = row as Record<string, unknown>;
      return {
        id: String(d.id),
        order_reference: String(d.order_reference ?? ""),
        status: String(d.status ?? "OPEN"),
        reason: String(d.reason ?? ""),
        description: d.description ? String(d.description) : undefined,
        created_at: String(d.created_at ?? ""),
      };
    });
  },

  retrieve: async (id: string): Promise<Dispute> => {
    const { data } = await apiClient.get<Dispute>(`/disputes/api/disputes/${id}/`);
    return data;
  },

  create: async (payload: {
    order: string;
    reason: string;
    description: string;
  }): Promise<Dispute> => {
    const { data } = await apiClient.post<Dispute>("/disputes/api/disputes/", payload);
    return data;
  },
};
