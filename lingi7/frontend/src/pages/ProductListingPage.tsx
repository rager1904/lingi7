import React, { useDeferredValue, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { productsApi } from "../api/resources";
import { formatZMW } from "../utils";
import { useCartStore } from "../store";
import type { Category, ProductListItem } from "../types";

const ProductListingPage: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const [products, setProducts] = useState<ProductListItem[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [selectedCategory, setSelectedCategory] = useState(params.get("category") ?? "");
  const [sort, setSort] = useState("featured");
  const [view, setView] = useState<"grid" | "list">("grid");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [compareIds, setCompareIds] = useState<number[]>([]);
  const deferredQuery = useDeferredValue(query);

  useEffect(() => { productsApi.categories().then(setCategories).catch(() => setCategories([])); }, []);
  useEffect(() => {
    setLoading(true); setError(false);
    productsApi.list({ page: 1, search: deferredQuery || undefined, category: selectedCategory || undefined })
      .then((result) => setProducts(result.results)).catch(() => setError(true)).finally(() => setLoading(false));
  }, [deferredQuery, selectedCategory]);

  const sorted = useMemo(() => [...products].sort((a, b) => sort === "price-asc" ? Number(a.price_zmw) - Number(b.price_zmw) : sort === "price-desc" ? Number(b.price_zmw) - Number(a.price_zmw) : a.name.localeCompare(b.name)), [products, sort]);
  const updateSearch = (value: string) => { setQuery(value); setParams(value ? { q: value } : {}); };
  const toggleCompare = (id: number) => setCompareIds((current) => current.includes(id) ? current.filter((item) => item !== id) : current.length < 3 ? [...current, id] : current);
  const compareProducts = sorted.filter((product) => compareIds.includes(product.id));

  return <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
    <nav className="mb-7 text-sm text-slate-500"><Link to="/" className="hover:text-blue-600">Home</Link> <span className="px-2">/</span> Shop</nav>
    <div className="mb-8 flex flex-col justify-between gap-5 lg:flex-row lg:items-end"><div><h1 className="text-4xl font-black tracking-tight text-slate-950">Find your next favorite.</h1><p className="mt-2 text-slate-500">Search verified stores and one-of-a-kind finds.</p></div><label className="flex w-full max-w-md items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm"><span className="text-slate-400">⌕</span><input value={query} onChange={(e) => updateSearch(e.target.value)} className="min-w-0 flex-1 bg-transparent text-sm outline-none" placeholder="Search products or brands" aria-label="Search products" /></label></div>
    <div className="mb-7 flex gap-2 overflow-x-auto pb-1">{[{slug:"", name:"All"}, ...categories].map((category) => <button key={category.slug || "all"} onClick={() => setSelectedCategory(category.slug)} className={`shrink-0 rounded-full px-4 py-2 text-sm font-semibold transition ${selectedCategory === category.slug ? "bg-slate-950 text-white" : "border border-slate-200 bg-white text-slate-600 hover:border-blue-300"}`}>{category.name}</button>)}</div>
    <div className="mb-6 flex items-center justify-between border-y border-slate-200 py-4"><p className="text-sm text-slate-500">{loading ? "Finding the best results..." : `${sorted.length} products`}</p><div className="flex items-center gap-2"><select value={sort} onChange={(e) => setSort(e.target.value)} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"><option value="featured">Featured</option><option value="price-asc">Price: low to high</option><option value="price-desc">Price: high to low</option></select><button onClick={() => setView(view === "grid" ? "list" : "grid")} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700" aria-label="Change product layout">{view === "grid" ? "☷" : "▦"}</button></div></div>
    {error ? <div className="rounded-2xl border border-red-100 bg-red-50 p-10 text-center"><h2 className="font-bold text-red-800">We couldn’t load the catalogue.</h2><p className="mt-1 text-sm text-red-700">Check your connection and try again.</p></div> : loading ? <Skeletons /> : sorted.length ? <div className={view === "grid" ? "grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" : "space-y-4"}>{sorted.map((product) => <ListingCard key={product.id} product={product} view={view} comparing={compareIds.includes(product.id)} onCompare={() => toggleCompare(product.id)} />)}</div> : <div className="rounded-3xl border border-dashed border-slate-300 bg-white p-16 text-center"><p className="text-4xl">⌕</p><h2 className="mt-4 text-xl font-black">No matches yet.</h2><p className="mt-2 text-slate-500">Try a different search or browse another category.</p><button onClick={() => { setQuery(""); setSelectedCategory(""); setParams({}); }} className="mt-5 text-sm font-bold text-blue-600">Clear filters</button></div>}
    {compareProducts.length > 0 && <aside aria-label="Product comparison" className="sticky bottom-4 mt-8 rounded-2xl border border-blue-100 bg-slate-950 p-4 text-white shadow-2xl"><div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-xs font-bold tracking-[.14em] text-cyan-300">AI COMPARISON</p><p className="mt-1 text-sm text-slate-200">{compareProducts.map((product) => product.name).join(" · ")}</p></div><div className="flex gap-2"><button onClick={() => setCompareIds([])} className="rounded-xl px-3 py-2 text-sm font-bold text-slate-300">Clear</button><button onClick={() => window.alert(`Lingi comparison ready: ${compareProducts.map((product) => `${product.name} (${formatZMW(product.price_zmw)})`).join(" vs ")}`)} className="rounded-xl bg-white px-4 py-2 text-sm font-bold text-slate-950">Compare {compareProducts.length}</button></div></div></aside>}
  </main>;
};

const ListingCard = ({ product, view, comparing, onCompare }: {product: ProductListItem; view: "grid" | "list"; comparing: boolean; onCompare: () => void}) => {
  const add = useCartStore((s) => s.addItem);
  return <article className={`group overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition hover:-translate-y-0.5 hover:shadow-lg ${view === "list" ? "flex" : ""}`}><Link to={`/products/${product.slug}`} className={`grid shrink-0 place-items-center bg-gradient-to-br from-blue-50 via-white to-violet-100 ${view === "list" ? "h-36 w-36" : "aspect-square"}`}>{product.primary_image_url ? <img src={product.primary_image_url} alt={product.name} loading="lazy" className="h-full w-full object-cover" /> : <span className="text-6xl text-blue-300">✦</span>}</Link><div className="flex min-w-0 flex-1 flex-col p-4"><div className="flex items-start justify-between gap-2"><p className="text-xs font-medium text-slate-400">{product.store_name}</p><button onClick={onCompare} aria-pressed={comparing} className={`rounded-lg px-2 py-1 text-xs font-bold ${comparing ? "bg-blue-600 text-white" : "bg-blue-50 text-blue-700"}`}>{comparing ? "Selected" : "Compare"}</button></div><Link to={`/products/${product.slug}`}><h2 className="mt-1 line-clamp-2 font-semibold text-slate-900">{product.name}</h2></Link><div className="mt-auto flex items-end justify-between pt-4"><div><p className="font-black text-slate-950">{formatZMW(product.price_zmw)}</p><p className="text-xs text-amber-500">★ 4.8</p></div><button disabled={!product.in_stock} onClick={() => add({ product_id: product.id, product_name: product.name, price_zmw: product.price_zmw, image_url: product.primary_image_url, max_stock: product.stock_quantity, seller_id: product.seller_id ?? "" }, 1)} className="rounded-xl bg-slate-950 px-3 py-2 text-sm font-bold text-white hover:bg-blue-600 disabled:bg-slate-200">Add</button></div></div></article>;
};
const Skeletons = () => <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{Array.from({ length: 8 }, (_, i) => <div key={i} className="animate-pulse overflow-hidden rounded-2xl border border-slate-100 bg-white"><div className="aspect-square bg-slate-100" /><div className="space-y-3 p-4"><div className="h-3 w-1/3 rounded bg-slate-100" /><div className="h-4 rounded bg-slate-100" /><div className="h-4 w-2/3 rounded bg-slate-100" /></div></div>)}</div>;
export default ProductListingPage;
