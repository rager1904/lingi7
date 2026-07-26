import React, { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { vendorApi, type VendorProduct } from "../api/vendor";
import { extractMessage, formatZMW } from "../utils";
import { PageEmpty, PageError, PageLoading } from "../components/feedback/PageStates";

const labels: Record<string, { title: string; intro: string }> = {
  inventory: { title: "Inventory", intro: "Keep availability accurate before customers discover an item." },
  customers: { title: "Customers", intro: "A privacy-respecting view of purchase relationships and service opportunities." },
  coupons: { title: "Coupons", intro: "Plan offers with clear guardrails and redemption visibility." },
  discounts: { title: "Discounts", intro: "Schedule store-wide and product-specific pricing moments." },
  reviews: { title: "Reviews", intro: "Listen to buyers and respond to feedback with care." },
};

const VendorOperationsPage: React.FC = () => {
  const { pathname } = useLocation();
  const key = pathname.split("/").pop() ?? "inventory";
  const config = labels[key] ?? labels.inventory;
  const [products, setProducts] = useState<VendorProduct[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => { vendorApi.listProducts().then(setProducts).catch((err) => setError(extractMessage(err))).finally(() => setLoading(false)); }, []);
  const inventoryRows = useMemo(() => products.map((product) => [product.name, product.sku || "—", formatZMW(product.price), product.status]), [products]);
  const fallback = key === "reviews" ? [["No reviews yet", "Invite customers after delivery", "—", "Ready"]] : [["Workspace ready", "Connect live data as endpoints become available", "—", "Ready"]];
  const rows = key === "inventory" ? inventoryRows : fallback;
  return <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8"><div className="mb-8 flex flex-col justify-between gap-5 sm:flex-row sm:items-end"><div><p className="text-xs font-bold tracking-[.18em] text-blue-600">SELLER WORKSPACE</p><h1 className="mt-2 text-4xl font-black tracking-tight text-slate-950">{config.title}</h1><p className="mt-2 max-w-2xl text-slate-500">{config.intro}</p></div><Link to="/vendor" className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700">Dashboard</Link></div><nav aria-label="Seller operations" className="mb-8 flex gap-2 overflow-x-auto pb-2">{Object.keys(labels).map((item) => <Link key={item} to={`/vendor/${item}`} className={`whitespace-nowrap rounded-full px-4 py-2 text-sm font-semibold capitalize ${key === item ? "bg-slate-950 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200"}`}>{item}</Link>)}</nav>{loading ? <PageLoading label="Loading your seller data…" /> : error ? <PageError message={error} onRetry={() => window.location.reload()} /> : rows.length === 0 ? <PageEmpty title="No products yet" description="Create a product to begin tracking availability." action={<Link to="/vendor/products" className="rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-bold text-white">Manage products</Link>} /> : <section className="overflow-hidden rounded-3xl bg-white shadow-sm ring-1 ring-slate-200"><div className="flex items-center justify-between border-b border-slate-100 p-6"><div><h2 className="font-bold text-slate-950">{key === "inventory" ? "Live product availability" : "Operational workspace"}</h2><p className="mt-1 text-sm text-slate-500">Data is kept scoped to your store.</p></div><button className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-bold text-white">Create new</button></div><div className="overflow-x-auto"><table className="min-w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr>{["Name", "Reference", "Detail", "Status"].map((header) => <th key={header} className="px-6 py-4">{header}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">{rows.map((row) => <tr key={row[0]}>{row.map((value, index) => <td key={`${value}-${index}`} className="px-6 py-5 text-slate-700">{index === 3 ? <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-700">{value}</span> : value}</td>)}</tr>)}</tbody></table></div></section>}</main>;
};
export default VendorOperationsPage;
