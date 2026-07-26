/**
 * Maps backend product serializers to frontend product types.
 */

import type { Category, Product, ProductImage, ProductListItem } from "../types";

interface ApiProductList {
  id: number;
  name: string;
  slug: string;
  price: string | number;
  primary_image?: string | null;
  store_name: string;
  category_name: string;
  seller_id?: string;
  is_in_stock?: boolean;
  stock_quantity?: number;
}

interface ApiProductImage {
  id: number;
  image: string;
  alt_text?: string;
  position?: number;
}

interface ApiProductDetail extends ApiProductList {
  description: string;
  store_slug: string;
  is_in_stock?: boolean;
  images?: ApiProductImage[];
  category?: Category;
  features?: string[];
  specs?: Record<string, string>;
  tags?: string[];
  descriptions_i18n?: Record<string, string>;
  meta_title?: string;
  meta_description?: string;
}

function resolveStock(raw: ApiProductList): { inStock: boolean; quantity: number } {
  const inStock = raw.is_in_stock !== false;
  const quantity =
    typeof raw.stock_quantity === "number"
      ? Math.max(0, raw.stock_quantity)
      : inStock
      ? 99
      : 0;
  return { inStock, quantity: inStock ? quantity : 0 };
}

export function mapApiProductListItem(raw: ApiProductList): ProductListItem {
  const { inStock, quantity } = resolveStock(raw);
  return {
    id: raw.id,
    name: raw.name,
    slug: raw.slug,
    price_zmw: String(raw.price),
    primary_image_url: raw.primary_image ?? null,
    category_name: raw.category_name,
    store_name: raw.store_name,
    stock_quantity: quantity,
    in_stock: inStock,
    seller_id: raw.seller_id,
  };
}

export function mapApiProductDetail(raw: ApiProductDetail): Product {
  const images: ProductImage[] = (raw.images ?? []).map((img) => ({
    id: img.id,
    image_url: img.image,
    is_primary: (img.position ?? 0) === 0,
    order: img.position ?? 0,
  }));

  const { inStock, quantity } = resolveStock(raw);

  return {
    id: raw.id,
    name: raw.name,
    slug: raw.slug,
    description: raw.description ?? "",
    price_zmw: String(raw.price),
    stock_quantity: quantity,
    in_stock: inStock,
    category: raw.category ?? { id: 0, name: raw.category_name, slug: "", parent: null },
    store_name: raw.store_name,
    store_slug: raw.store_slug,
    seller_id: raw.seller_id,
    images,
    status: "APPROVED",
    created_at: new Date().toISOString(),
    features: raw.features ?? [],
    specs: raw.specs ?? {},
    tags: raw.tags ?? [],
    descriptions_i18n: raw.descriptions_i18n ?? {},
    meta_title: raw.meta_title,
    meta_description: raw.meta_description,
  };
}

export function normalizeProductListResponse(data: unknown): ApiProductList[] {
  if (Array.isArray(data)) return data as ApiProductList[];
  if (data && typeof data === "object" && Array.isArray((data as { results?: unknown }).results)) {
    return (data as { results: ApiProductList[] }).results;
  }
  return [];
}
