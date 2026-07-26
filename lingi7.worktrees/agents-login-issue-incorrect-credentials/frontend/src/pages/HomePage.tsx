/**
 * HomePage — product catalogue with search and category filter
 */

import React, { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { productsApi } from "../api/resources";
import { useCartStore } from "../store";
import { formatZMW } from "../utils";
import type { ProductListItem } from "../types";

const CATEGORIES = [
  { slug: "", label: "All" },
  { slug: "electronics", label: "Electronics" },
  { slug: "clothing", label: "Clothing" },
  { slug: "household", label: "Household" },
  { slug: "food", label: "Food" },
  { slug: "beauty", label: "Beauty" },
];

const HomePage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const autoFocusSearch = searchParams.get("search") === "1";

  const [products, setProducts] = useState<ProductListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const searchRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-focus search if redirected from top bar icon
  useEffect(() => {
    if (autoFocusSearch) searchRef.current?.focus();
  }, [autoFocusSearch]);

  const fetchProducts = async (p: number, q: string, cat: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const resp = await productsApi.list({ page: p, search: q || undefined, category: cat || undefined });
      setProducts((prev) => (p === 1 ? resp.results : [...prev, ...resp.results]));
      setHasMore(!!resp.next);
    } catch {
      setError("Failed to load products. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  // Debounced search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setPage(1);
      fetchProducts(1, search, category);
    }, 350);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [search, category]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadMore = () => {
    const next = page + 1;
    setPage(next);
    fetchProducts(next, search, category);
  };

  return (
    <div className="mx-auto max-w-2xl px-4 py-4">
      {/* Search bar */}
      <div className="relative mb-4">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
          fill="none" viewBox="0 0 24 24" stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
        </svg>
        <input
          ref={searchRef}
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search products..."
          className="w-full rounded-xl border border-gray-200 bg-white py-2.5 pl-9 pr-4 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
        />
      </div>

      {/* Category pills */}
      <div className="mb-4 flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
        {CATEGORIES.map(({ slug, label }) => (
          <button
            key={slug}
            onClick={() => setCategory(slug)}
            className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
              category === slug
                ? "bg-emerald-600 text-white"
                : "bg-white border border-gray-200 text-gray-600"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <p className="mb-4 text-center text-sm text-red-600">{error}</p>
      )}

      {/* Grid */}
      {isLoading && products.length === 0 ? (
        <ProductGridSkeleton />
      ) : products.length === 0 ? (
        <div className="py-16 text-center">
          <p className="text-gray-500">No products found.</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3">
            {products.map((p) => (
              <ProductCard key={p.id} product={p} />
            ))}
          </div>

          {hasMore && (
            <button
              onClick={loadMore}
              disabled={isLoading}
              className="mt-6 w-full rounded-xl border border-gray-300 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              {isLoading ? "Loading..." : "Load More"}
            </button>
          )}
        </>
      )}
    </div>
  );
};

// ── ProductCard ───────────────────────────────────────────────────────────────

const ProductCard: React.FC<{ product: ProductListItem }> = ({ product }) => {
  const addItem = useCartStore((s) => s.addItem);

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
      <Link to={`/products/${product.slug}`}>
        <div className="aspect-square bg-gray-100">
          {product.primary_image_url ? (
            <img
              src={product.primary_image_url}
              alt={product.name}
              className="h-full w-full object-cover"
              loading="lazy"
            />
          ) : (
            <div className="flex h-full items-center justify-center text-3xl text-gray-300">📦</div>
          )}
        </div>
      </Link>
      <div className="p-3">
        <Link to={`/products/${product.slug}`}>
          <p className="text-xs text-gray-500 truncate">{product.store_name}</p>
          <p className="mt-0.5 text-sm font-semibold text-gray-900 line-clamp-2 leading-tight">
            {product.name}
          </p>
        </Link>
        <div className="mt-2 flex items-center justify-between">
          <span className="text-sm font-bold text-emerald-700">
            {formatZMW(product.price_zmw)}
          </span>
          <button
            onClick={() =>
              addItem({
                product_id: product.id,
                product_name: product.name,
                price_zmw: product.price_zmw,
                image_url: product.primary_image_url,
                max_stock: product.stock_quantity,
              })
            }
            disabled={product.stock_quantity === 0}
            aria-label={`Add ${product.name} to cart`}
            className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:bg-gray-200 disabled:text-gray-400"
          >
            <span className="text-base leading-none">+</span>
          </button>
        </div>
        {product.stock_quantity === 0 && (
          <p className="mt-1 text-xs text-red-500">Out of stock</p>
        )}
      </div>
    </div>
  );
};

const ProductGridSkeleton: React.FC = () => (
  <div className="grid grid-cols-2 gap-3">
    {[...Array(6)].map((_, i) => (
      <div key={i} className="rounded-xl border border-gray-100 bg-gray-100 animate-pulse">
        <div className="aspect-square bg-gray-200 rounded-t-xl" />
        <div className="p-3 space-y-2">
          <div className="h-3 w-3/4 bg-gray-200 rounded" />
          <div className="h-4 w-full bg-gray-200 rounded" />
          <div className="h-4 w-1/2 bg-gray-200 rounded" />
        </div>
      </div>
    ))}
  </div>
);

export default HomePage;
