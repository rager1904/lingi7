import React from "react";
import { Link } from "react-router-dom";
import { useWishlist } from "../hooks";
import { useAuthStore, useWishlistStore } from "../store";
import { formatZMW } from "../utils";
import type { WishlistItem } from "../types";

const WishlistPage: React.FC = () => {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const { data, isLoading, error, removeFromWishlist } = useWishlist();
  const totalCount = useWishlistStore((s) => s.totalCount);

  if (!isAuthenticated) {
    return (
      <main className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
        <p className="text-sm font-bold tracking-[.16em] text-blue-600">SAVED</p>
        <h1 className="mt-2 text-4xl font-black tracking-tight text-slate-950">Your wishlist.</h1>
        <div className="mt-8 rounded-3xl border border-dashed border-slate-300 bg-white px-6 py-20 text-center">
          <p className="text-5xl">♡</p>
          <h2 className="mt-5 text-xl font-black text-slate-950">Sign in to save products</h2>
          <p className="mt-2 text-sm text-slate-500">Create an account to heart products and build your wishlist.</p>
          <Link to="/login" className="mt-6 inline-flex rounded-xl bg-slate-950 px-5 py-3 text-sm font-bold text-white hover:bg-blue-600">
            Sign in
          </Link>
        </div>
      </main>
    );
  }

  if (isLoading) {
    return (
      <main className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
        <p className="text-sm font-bold tracking-[.16em] text-blue-600">SAVED</p>
        <h1 className="mt-2 text-4xl font-black tracking-tight text-slate-950">Your wishlist.</h1>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="animate-pulse overflow-hidden rounded-2xl border border-slate-100 bg-white">
              <div className="aspect-square bg-slate-100" />
              <div className="space-y-3 p-4">
                <div className="h-3 w-1/3 rounded bg-slate-100" />
                <div className="h-4 rounded bg-slate-100" />
                <div className="h-4 w-2/3 rounded bg-slate-100" />
              </div>
            </div>
          ))}
        </div>
      </main>
    );
  }

  const items = data?.results ?? [];

  return (
    <main className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
      <p className="text-sm font-bold tracking-[.16em] text-blue-600">SAVED</p>
      <h1 className="mt-2 text-4xl font-black tracking-tight text-slate-950">Your wishlist.</h1>
      <p className="mt-2 text-sm text-slate-500">
        {totalCount > 0 ? `${totalCount} product${totalCount === 1 ? "" : "s"} saved` : "No saved products yet"}
      </p>

      {error ? (
        <div className="mt-8 rounded-2xl border border-red-100 bg-red-50 p-10 text-center">
          <h2 className="font-bold text-red-800">Couldn't load your wishlist</h2>
          <p className="mt-1 text-sm text-red-700">Check your connection and try again.</p>
        </div>
      ) : items.length === 0 ? (
        <div className="mt-8 rounded-3xl border border-dashed border-slate-300 bg-white px-6 py-20 text-center">
          <p className="text-5xl">♡</p>
          <h2 className="mt-5 text-xl font-black text-slate-950">Save the things you love.</h2>
          <p className="mt-2 text-sm text-slate-500">Tap the heart on any product to collect it here.</p>
          <Link to="/shop" className="mt-6 inline-flex rounded-xl bg-slate-950 px-5 py-3 text-sm font-bold text-white hover:bg-blue-600">
            Discover products
          </Link>
        </div>
      ) : (
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <WishlistCard key={item.id} item={item} onRemove={() => removeFromWishlist(item.id)} />
          ))}
        </div>
      )}
    </main>
  );
};

// ─── Wishlist Card ────────────────────────────────────────────────────────────

const WishlistCard: React.FC<{ item: WishlistItem; onRemove: () => void }> = ({ item, onRemove }) => {
  const product = item.product_detail;

  return (
    <article className="group overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition hover:-translate-y-0.5 hover:shadow-lg">
      <Link to={`/products/${product.slug}`} className="grid aspect-square place-items-center bg-gradient-to-br from-blue-50 via-white to-violet-100">
        {product.primary_image_url ? (
          <img src={product.primary_image_url} alt={product.name} loading="lazy" className="h-full w-full object-cover" />
        ) : (
          <span className="text-6xl text-blue-300">✦</span>
        )}
      </Link>
      <div className="p-4">
        <p className="text-xs font-medium text-slate-400">{product.store_name}</p>
        <Link to={`/products/${product.slug}`}>
          <h3 className="mt-1 line-clamp-2 font-semibold text-slate-900">{product.name}</h3>
        </Link>
        <div className="mt-3 flex items-center justify-between">
          <span className="font-black text-slate-950">{formatZMW(product.price_zmw)}</span>
          <div className="flex items-center gap-2">
            <span className={`text-xs font-bold ${product.in_stock ? "text-emerald-600" : "text-red-600"}`}>
              {product.in_stock ? "In stock" : "Sold out"}
            </span>
          </div>
        </div>
        {item.note && <p className="mt-2 text-xs text-slate-400 italic">"{item.note}"</p>}
        <div className="mt-3 flex gap-2">
          <Link
            to={`/products/${product.slug}`}
            className="flex-1 rounded-xl bg-slate-950 py-2.5 text-center text-sm font-bold text-white transition hover:bg-blue-600"
          >
            View product
          </Link>
          <button
            onClick={onRemove}
            className="rounded-xl border border-slate-200 px-3 py-2.5 text-sm font-bold text-slate-600 transition hover:border-red-200 hover:text-red-600"
            aria-label="Remove from wishlist"
          >
            ✕
          </button>
        </div>
      </div>
    </article>
  );
};

export default WishlistPage;
