import apiClient from "./client";
import {
  mapApiProductDetail,
  mapApiProductListItem,
  normalizeProductListResponse,
} from "./productMappers";
import type { Category, PaginatedResponse, Product, ProductListItem } from "../types";

export const productsApi = {
  list: async (params?: {
    page?: number;
    category?: string;
    q?: string;
    search?: string;
    min_price?: number;
    max_price?: number;
    store?: string;
  }): Promise<PaginatedResponse<ProductListItem>> => {
    const query = {
      ...params,
      q: params?.q ?? params?.search,
    };
    const { data } = await apiClient.get<unknown>("/products/products/", { params: query });
    const rawList = normalizeProductListResponse(data);
    const results = rawList.map(mapApiProductListItem);
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

  retrieve: async (slug: string): Promise<Product> => {
    const { data } = await apiClient.get<unknown>(`/products/products/${slug}/`);
    return mapApiProductDetail(data as Parameters<typeof mapApiProductDetail>[0]);
  },

  categories: async (): Promise<Category[]> => {
    const { data } = await apiClient.get<unknown>("/products/categories/");
    if (Array.isArray(data)) return data as Category[];
    if (data && typeof data === "object" && Array.isArray((data as { results?: unknown }).results)) {
      return (data as { results: Category[] }).results;
    }
    return [];
  },
};
