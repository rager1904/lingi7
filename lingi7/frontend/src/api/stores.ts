import apiClient from "./client";
import type { PaginatedResponse, PublicStore } from "../types";

const normalize = (data: unknown): PaginatedResponse<PublicStore> => {
  if (Array.isArray(data)) return { count: data.length, next: null, previous: null, results: data as PublicStore[] };
  const page = data as Partial<PaginatedResponse<PublicStore>>;
  return { count: page.count ?? 0, next: page.next ?? null, previous: page.previous ?? null, results: page.results ?? [] };
};

export const storesApi = {
  list: async (): Promise<PaginatedResponse<PublicStore>> => normalize((await apiClient.get<unknown>("/products/stores/")).data),
  retrieve: async (slug: string): Promise<PublicStore> => (await apiClient.get<PublicStore>(`/products/stores/${slug}/`)).data,
};
