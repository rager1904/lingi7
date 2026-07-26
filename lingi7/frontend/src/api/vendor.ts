import apiClient from "./client";

export interface VendorDashboard {
  store_name: string;
  store_status: string;
  total_products: number;
  pending_listings: number;
  active_listings: number;
  orders_pending_shipment: number;
  escrow_held_zmw: string;
  total_gmv_zmw: string;
  dispute_rate_pct: string;
  last_payout_at: string | null;
  last_payout_zmw: string | null;
}

export interface VendorStore {
  id: number;
  name: string;
  slug: string;
  status: string;
  description?: string;
  logo?: string | null;
  banner?: string | null;
  business_type?: string;
  payout_account?: string;
  payout_provider?: string;
  rejection_reason?: string;
  created_at?: string;
}

export type ProductCondition = "NEW" | "USED" | "REFURBISHED";

export type EnrichmentStatus =
  | "PENDING"
  | "PROCESSING"
  | "COMPLETED"
  | "FAILED"
  | "DISABLED";

export interface ProductEnrichment {
  enrichment_status: EnrichmentStatus;
  enriched_at: string | null;
  enrichment_error?: string;
  meta_title?: string;
  meta_description?: string;
  search_keywords?: string[];
  ai_enhanced_title?: string;
  ai_features?: string[];
  ai_specs?: Record<string, unknown>;
  suggested_category?: number | null;
  suggested_category_name?: string | null;
  suggested_tags?: string[];
  image_quality_scores?: {
    overall?: number;
    recommendations?: string[];
  };
  descriptions_i18n?: Record<string, string>;
}

export interface VendorProduct {
  id: number;
  name: string;
  slug: string;
  description: string;
  category: number;
  price: string;
  compare_at_price?: string | null;
  sku?: string;
  condition?: ProductCondition;
  weight_kg?: string | null;
  ships_from?: string;
  status: string;
  rejection_reason?: string;
  enrichment_status?: EnrichmentStatus;
  enriched_at?: string | null;
}

export interface VendorStoreRegistration {
  name: string;
  description?: string;
  business_type: "INDIVIDUAL" | "REGISTERED";
  tpin?: string;
  nrc_or_reg_no: string;
  business_address: string;
  phone_number: string;
  payout_account: string;
  payout_provider: "MTN" | "AIRTEL";
  id_document: File;
}

export interface UpdateVendorStorePayload {
  name?: string;
  description?: string;
  logo?: File | null;
  banner?: File | null;
}

export interface CreateVendorProductPayload {
  name: string;
  description: string;
  category: number;
  price: string | number;
  sku?: string;
  condition?: ProductCondition;
  compare_at_price?: string | number | null;
  weight_kg?: string | number | null;
  ships_from?: string;
  initial_quantity?: number;
  track_inventory?: boolean;
}

export const vendorApi = {
  dashboard: async (): Promise<VendorDashboard> => {
    const { data } = await apiClient.get<VendorDashboard>(
      "/products/vendor/dashboard/"
    );
    return data;
  },

  storeMe: async (): Promise<VendorStore> => {
    const { data } = await apiClient.get<VendorStore>("/products/vendor/store/me/");
    return data;
  },

  registerStore: async (payload: VendorStoreRegistration): Promise<VendorStore> => {
    const form = new FormData();
    form.append("name", payload.name);
    form.append("description", payload.description ?? "");
    form.append("business_type", payload.business_type);
    if (payload.tpin) form.append("tpin", payload.tpin);
    form.append("nrc_or_reg_no", payload.nrc_or_reg_no);
    form.append("business_address", payload.business_address);
    form.append("phone_number", payload.phone_number);
    form.append("payout_account", payload.payout_account);
    form.append("payout_provider", payload.payout_provider);
    form.append("id_document", payload.id_document, payload.id_document.name);

    const { data } = await apiClient.post<VendorStore>(
      "/products/vendor/store/register/",
      form
    );
    return data;
  },

  updateStore: async (payload: UpdateVendorStorePayload): Promise<VendorStore> => {
    const form = new FormData();
    if (payload.name !== undefined) form.append("name", payload.name);
    if (payload.description !== undefined) form.append("description", payload.description);
    if (payload.logo) form.append("logo", payload.logo, payload.logo.name);
    if (payload.banner) form.append("banner", payload.banner, payload.banner.name);
    const { data } = await apiClient.patch<VendorStore>("/products/vendor/store/update/", form);
    return data;
  },

  listProducts: async (): Promise<VendorProduct[]> => {
    const { data } = await apiClient.get<unknown>("/products/vendor/products/");
    if (Array.isArray(data)) return data as VendorProduct[];
    if (
      data &&
      typeof data === "object" &&
      Array.isArray((data as { results?: unknown }).results)
    ) {
      return (data as { results: VendorProduct[] }).results;
    }
    return [];
  },

  createProduct: async (payload: CreateVendorProductPayload): Promise<VendorProduct> => {
    const body: Record<string, unknown> = {
      name: payload.name,
      description: payload.description,
      category: payload.category,
      price: payload.price,
      condition: payload.condition ?? "NEW",
      track_inventory: payload.track_inventory ?? true,
      initial_quantity: payload.initial_quantity ?? 0,
    };
    if (payload.sku) body.sku = payload.sku;
    if (payload.compare_at_price) body.compare_at_price = payload.compare_at_price;
    if (payload.weight_kg) body.weight_kg = payload.weight_kg;
    if (payload.ships_from) body.ships_from = payload.ships_from;

    const { data } = await apiClient.post<VendorProduct>(
      "/products/vendor/products/",
      body
    );
    return data;
  },

  uploadProductImage: async (
    productId: number,
    image: File,
    altText = ""
  ): Promise<void> => {
    const form = new FormData();
    form.append("image", image, image.name);
    if (altText) form.append("alt_text", altText);
    await apiClient.post(`/products/vendor/products/${productId}/images/`, form);
  },

  submitProduct: async (productId: number): Promise<VendorProduct> => {
    const { data } = await apiClient.post<VendorProduct>(
      `/products/vendor/products/${productId}/submit/`
    );
    return data;
  },

  enrichProduct: async (
    productId: number
  ): Promise<{ detail: string; enrichment_status: EnrichmentStatus }> => {
    const { data } = await apiClient.post<{
      detail: string;
      enrichment_status: EnrichmentStatus;
    }>(`/products/vendor/products/${productId}/enrich/`);
    return data;
  },

  getEnrichment: async (productId: number): Promise<ProductEnrichment> => {
    const { data } = await apiClient.get<ProductEnrichment>(
      `/products/vendor/products/${productId}/enrichment/`
    );
    return data;
  },

  applyEnrichment: async (
    productId: number,
    fields: Array<"title" | "description" | "category" | "seo">
  ): Promise<VendorProduct> => {
    const { data } = await apiClient.post<VendorProduct>(
      `/products/vendor/products/${productId}/enrichment/apply/`,
      { fields }
    );
    return data;
  },
};
