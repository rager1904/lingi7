/**
 * VendorDashboardPage — GET /api/v1/products/vendor/dashboard/
 */

import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { vendorApi, type VendorDashboard, type VendorStore } from "../api/vendor";
import { useAuthStore } from "../store";
import { formatZMW, extractMessage } from "../utils";

const VendorDashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [data, setData] = useState<VendorDashboard | null>(null);
  const [store, setStore] = useState<VendorStore | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (user?.role !== "VENDOR") {
      navigate("/account", { replace: true });
      return;
    }

    Promise.all([
      vendorApi.dashboard().catch((err) => {
        throw err;
      }),
      vendorApi.storeMe().catch(() => null),
    ])
      .then(([dashboard, storeInfo]) => {
        setData(dashboard);
        setStore(storeInfo);
      })
      .catch(async (err) => {
        const msg = extractMessage(err);
        const storeInfo = await vendorApi.storeMe().catch(() => null);
        setStore(storeInfo);
        setError(msg);
      })
      .finally(() => setLoading(false));
  }, [user, navigate]);

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 text-center text-sm text-gray-500">
        Loading dashboard...
      </div>
    );
  }

  if (error) {
    const pendingStore = store && store.status === "PENDING";
    const rejectedStore = store && store.status === "REJECTED";
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 text-center space-y-4">
        <p className="text-red-600">{error}</p>
        {pendingStore && (
          <p className="text-sm text-gray-600">
            Your store <strong>{store.name}</strong> is pending admin approval. You can manage
            listings once it is approved.
          </p>
        )}
        {rejectedStore && (
          <p className="text-sm text-gray-600">
            Store rejected: {store.rejection_reason || "See admin notes."}
          </p>
        )}
        {!store && (
          <Link to="/vendor/store" className="text-emerald-600 font-medium">
            Register your store →
          </Link>
        )}
        {store && (
          <Link to="/vendor/store" className="block text-sm text-emerald-600 font-medium">
            View store details →
          </Link>
        )}
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 space-y-5 sm:px-6 lg:px-8">
      <button onClick={() => navigate("/account")} className="text-sm text-gray-500 min-h-0">
        ← Account
      </button>
      <p className="text-sm font-bold tracking-[.16em] text-blue-600">SELLER WORKSPACE</p>
      <h1 className="text-4xl font-black tracking-tight text-slate-950">Vendor dashboard</h1>
      <p className="text-sm text-gray-500">
        {data.store_name} · {data.store_status}
      </p>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard label="Active listings" value={String(data.active_listings)} />
        <StatCard label="Pending review" value={String(data.pending_listings)} />
        <StatCard label="Orders to ship" value={String(data.orders_pending_shipment)} />
        <StatCard label="Escrow held" value={formatZMW(data.escrow_held_zmw)} />
        <StatCard label="Total GMV" value={formatZMW(data.total_gmv_zmw)} />
      </div>

      <Link
        to="/vendor/orders"
        className="block rounded-2xl border border-slate-200 bg-white p-5 text-center text-sm font-bold text-slate-800 shadow-sm hover:border-blue-200 hover:bg-blue-50"
      >
        Fulfil orders ({data.orders_pending_shipment}) →
      </Link>
      <Link
        to="/vendor/products"
        className="block rounded-2xl bg-slate-950 p-5 text-center text-sm font-bold text-white shadow-lg hover:bg-blue-700"
      >
        Manage products →
      </Link>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {[["Inventory", "/vendor/inventory"], ["Customers", "/vendor/customers"], ["Coupons", "/vendor/coupons"], ["Discounts", "/vendor/discounts"], ["Reviews", "/vendor/reviews"]].map(([label, href]) => <Link key={href} to={href} className="rounded-2xl border border-slate-200 bg-white p-4 text-center text-sm font-bold text-slate-700 shadow-sm hover:border-blue-200 hover:text-blue-700">{label}</Link>)}
      </div>
    </div>
  );
};

const StatCard: React.FC<{
  label: string;
  value: string;
  className?: string;
}> = ({ label, value, className = "" }) => (
  <div className={`rounded-2xl border border-slate-200 bg-white p-5 shadow-sm ${className}`}>
    <p className="text-xs font-bold uppercase tracking-wide text-slate-400">{label}</p>
    <p className="mt-2 text-xl font-black text-slate-950">{value}</p>
  </div>
);

export default VendorDashboardPage;
