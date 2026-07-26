import React, { useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { Link, useParams } from "react-router-dom";
import { productsApi } from "../api/resources";
import { useCartStore, useAuthStore, useWishlistStore } from "../store";
import { useSimilarProducts, useLikeToggle, useTrackView } from "../hooks";
import { formatZMW } from "../utils";
import type { Product, ProductListItem } from "../types";

type DetailTab = "Details" | "Specifications" | "Shipping";

const ProductDetailPage: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const addItem = useCartStore((s) => s.addItem);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeImage, setActiveImage] = useState(0);
  const [quantity, setQuantity] = useState(1);
  const [tab, setTab] = useState<DetailTab>("Details");
  const [added, setAdded] = useState(false);

  // Like integration
  const likeToggle = useLikeToggle();
  const likedIds = useWishlistStore((s) => s.likedProductIds);
  const [saved, setSaved] = useState(false);

  // Track view on mount
  const trackView = useTrackView();

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    productsApi
      .retrieve(slug)
      .then((p) => {
        setProduct(p);
        setSaved(likedIds.has(p.id));
        // Track the view
        if (isAuthenticated) {
          trackView.mutate(p.id);
        }
      })
      .catch(() => setError("This item is no longer available."))
      .finally(() => setLoading(false));
  }, [slug]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (product) document.title = `${product.name} | Lingi7`;
    return () => { document.title = "Lingi7"; };
  }, [product]);

  // Similar products
  const { data: similarProducts } = useSimilarProducts(product?.id ?? null, 8);

  const specs = useMemo(() => Object.entries(product?.specs ?? {}).filter(([key]) => key !== "threed_preview"), [product]);

  if (loading) return <DetailSkeleton />;
  if (!product || error) {
    return (
      <main className="mx-auto max-w-xl px-4 py-24 text-center">
        <p className="text-5xl">⌕</p>
        <h1 className="mt-5 text-2xl font-black">Product unavailable</h1>
        <p className="mt-2 text-slate-500">{error ?? "We couldn't find that product."}</p>
        <Link to="/shop" className="mt-6 inline-flex rounded-xl bg-slate-950 px-5 py-3 text-sm font-bold text-white">Back to shop</Link>
      </main>
    );
  }

  const inStock = product.in_stock !== false && product.stock_quantity > 0;
  const image = product.images[activeImage];
  const tags = product.tags ?? [];
  const features = product.features ?? [];

  const add = () => {
    addItem(
      {
        product_id: product.id,
        product_name: product.name,
        price_zmw: product.price_zmw,
        image_url: product.images[0]?.image_url ?? null,
        max_stock: product.stock_quantity,
        seller_id: product.seller_id ?? "",
      },
      quantity
    );
    toast.success(`${product.name} added to cart`);
    setAdded(true);
    window.setTimeout(() => setAdded(false), 1800);
  };

  const handleLike = () => {
    if (!isAuthenticated) {
      toast.error("Sign in to like products");
      return;
    }
    likeToggle.mutate(product.id);
    setSaved(!saved);
  };

  return (
    <main className="mx-auto max-w-7xl px-4 py-7 sm:px-6 lg:px-8">
      <nav className="mb-7 text-sm text-slate-500">
        <Link to="/" className="hover:text-blue-600">Home</Link>
        <span className="px-2">/</span>
        <Link to="/shop" className="hover:text-blue-600">Shop</Link>
        <span className="px-2">/</span>
        <span className="text-slate-700">{product.category.name}</span>
      </nav>

      <div className="grid gap-9 lg:grid-cols-[1.05fr_.95fr] lg:gap-14">
        {/* Image Gallery */}
        <section>
          <div className="relative grid aspect-square place-items-center overflow-hidden rounded-[28px] bg-gradient-to-br from-slate-100 via-white to-blue-100">
            <button
              onClick={handleLike}
              className={`absolute right-5 top-5 z-10 grid h-11 w-11 place-items-center rounded-full bg-white/90 text-xl shadow-sm transition-all ${
                saved ? "text-red-500" : "text-slate-700"
              }`}
              aria-label={saved ? "Unlike product" : "Like product"}
            >
              {saved ? "♥" : "♡"}
            </button>
            {image ? (
              <img
                src={image.image_url}
                alt={product.name}
                className="h-full w-full object-contain transition duration-500 hover:scale-105"
              />
            ) : (
              <span className="text-9xl text-blue-200">✦</span>
            )}
          </div>
          {product.images.length > 1 && (
            <div className="mt-4 flex gap-3 overflow-x-auto pb-1">
              {product.images.map((item, idx) => (
                <button
                  key={item.id}
                  onClick={() => setActiveImage(idx)}
                  className={`h-20 w-20 shrink-0 overflow-hidden rounded-xl border-2 bg-slate-100 ${
                    idx === activeImage ? "border-blue-600" : "border-transparent"
                  }`}
                >
                  <img src={item.image_url} alt="" className="h-full w-full object-cover" />
                </button>
              ))}
            </div>
          )}
        </section>

        {/* Product Info */}
        <section className="flex flex-col">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-bold text-blue-700">Verified seller</span>
            {inStock ? (
              <span className="text-xs font-semibold text-emerald-600">In stock</span>
            ) : (
              <span className="text-xs font-semibold text-red-600">Sold out</span>
            )}
          </div>

          <h1 className="mt-4 text-3xl font-black tracking-tight text-slate-950 sm:text-4xl">{product.name}</h1>
          <Link to={`/shops/${product.store_slug}`} className="mt-2 text-sm font-semibold text-blue-600 hover:text-blue-700">
            {product.store_name} →
          </Link>

          <div className="mt-5 flex items-baseline gap-3">
            <span className="text-4xl font-black text-slate-950">{formatZMW(product.price_zmw)}</span>
            {product.stock_quantity <= 5 && inStock && (
              <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-bold text-amber-700">Only {product.stock_quantity} left</span>
            )}
          </div>

          {tags.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {tags.slice(0, 5).map((tag) => (
                <span key={tag} className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">{tag}</span>
              ))}
            </div>
          )}

          {/* Tabs */}
          <div className="mt-8 flex gap-1 border-b border-slate-200">
            {(["Details", "Specifications", "Shipping"] as DetailTab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-4 py-3 text-sm font-semibold transition ${
                  tab === t ? "border-b-2 border-blue-600 text-blue-600" : "text-slate-500 hover:text-slate-700"
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          <div className="mt-5 min-h-[120px] text-sm leading-7 text-slate-600">
            {tab === "Details" && (
              <div>
                {features.length > 0 ? (
                  <ul className="space-y-2">{features.map((f) => <li key={f}>• {f}</li>)}</ul>
                ) : (
                  <p>{product.description}</p>
                )}
              </div>
            )}
            {tab === "Specifications" && (
              <div className="space-y-2">
                {specs.length > 0 ? specs.map(([k, v]) => (
                  <div key={k} className="flex justify-between border-b border-slate-100 py-2">
                    <span className="font-medium text-slate-700">{k}</span>
                    <span>{v}</span>
                  </div>
                )) : <p>No specifications available.</p>}
              </div>
            )}
            {tab === "Shipping" && (
              <div>
                <p>Ships from: <strong>{product.category.name}</strong></p>
                <p className="mt-2">Standard delivery within 3-7 business days across Zambia.</p>
                <p className="mt-2">Secure escrow-protected checkout via MTN MoMo or Airtel Money.</p>
              </div>
            )}
          </div>

          {/* Quantity + Actions */}
          <div className="mt-auto pt-8">
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium text-slate-700">Qty:</span>
              <div className="flex items-center rounded-xl border border-slate-200">
                <button onClick={() => setQuantity(Math.max(1, quantity - 1))} className="px-3 py-2 text-lg font-bold text-slate-600 hover:text-slate-900">−</button>
                <span className="min-w-[40px] text-center text-sm font-bold">{quantity}</span>
                <button onClick={() => setQuantity(Math.min(product.stock_quantity, quantity + 1))} className="px-3 py-2 text-lg font-bold text-slate-600 hover:text-slate-900">+</button>
              </div>
            </div>
            <div className="mt-4 flex gap-3">
              <button
                onClick={add}
                disabled={!inStock || added}
                className="flex-1 rounded-xl bg-slate-950 px-6 py-3.5 text-sm font-bold text-white transition hover:bg-blue-600 disabled:bg-slate-200 disabled:text-slate-400"
              >
                {added ? "Added to cart ✓" : "Add to cart"}
              </button>
              <button
                onClick={handleLike}
                className={`grid h-12 w-12 place-items-center rounded-xl border-2 transition-all ${
                  saved ? "border-red-200 bg-red-50 text-red-500" : "border-slate-200 bg-white text-slate-600 hover:border-red-200 hover:text-red-500"
                }`}
                aria-label={saved ? "Unlike" : "Like"}
              >
                {saved ? "♥" : "♡"}
              </button>
            </div>
          </div>
        </section>
      </div>

      {/* Similar Products */}
      {similarProducts && similarProducts.length > 0 && (
        <section className="mt-16">
          <h2 className="mb-6 text-2xl font-black tracking-tight text-slate-950">Similar products</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {similarProducts.map((p) => (
              <SimilarCard key={p.id} product={p} />
            ))}
          </div>
        </section>
      )}
    </main>
  );
};

// ─── Similar Product Card ─────────────────────────────────────────────────────

const SimilarCard: React.FC<{ product: ProductListItem }> = ({ product }) => (
  <Link
    to={`/products/${product.slug}`}
    className="group overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition hover:-translate-y-1 hover:shadow-lg"
  >
    <div className="grid aspect-square place-items-center bg-gradient-to-br from-blue-50 via-white to-violet-100">
      {product.primary_image_url ? (
        <img src={product.primary_image_url} alt={product.name} loading="lazy" className="h-full w-full object-cover" />
      ) : (
        <span className="text-5xl text-blue-300">✦</span>
      )}
    </div>
    <div className="p-4">
      <p className="text-xs text-slate-400">{product.category_name}</p>
      <h3 className="mt-1 line-clamp-2 font-semibold text-slate-900">{product.name}</h3>
      <div className="mt-3 flex items-center justify-between">
        <span className="font-black text-slate-950">{formatZMW(product.price_zmw)}</span>
        <span className={`text-xs font-bold ${product.in_stock ? "text-emerald-600" : "text-red-600"}`}>
          {product.in_stock ? "In stock" : "Sold out"}
        </span>
      </div>
    </div>
  </Link>
);

// ─── Skeleton ─────────────────────────────────────────────────────────────────

const DetailSkeleton = () => (
  <main className="mx-auto max-w-7xl animate-pulse px-4 py-8 sm:px-6">
    <div className="grid gap-10 lg:grid-cols-2">
      <div className="aspect-square rounded-[28px] bg-slate-100" />
      <div className="space-y-5 py-10">
        <div className="h-4 w-1/4 rounded bg-slate-100" />
        <div className="h-12 w-4/5 rounded bg-slate-100" />
        <div className="h-8 w-1/3 rounded bg-slate-100" />
        <div className="h-24 rounded-2xl bg-slate-100" />
      </div>
    </div>
  </main>
);

export default ProductDetailPage;
