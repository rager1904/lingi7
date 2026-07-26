/**
 * VendorOrdersPage — acknowledge and ship orders (seller fulfilment).
 */

import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ordersApi } from "../api/orders";
import { useAuthStore } from "../store";
import type { OrderListItem, OrderStatus } from "../types";
import { extractMessage, formatZMW, formatDate } from "../utils";

const FULFILMENT_STATUSES: OrderStatus[] = [
  "PAYMENT_RECEIVED",
  "PROCESSING",
  "SHIPPED",
];

const STATUS_LABEL: Partial<Record<OrderStatus, string>> = {
  PAYMENT_RECEIVED: "Paid — acknowledge to start packing",
  PROCESSING: "Processing — mark as shipped",
  SHIPPED: "Shipped — awaiting buyer confirmation",
};

const VendorOrdersPage: React.FC = () => {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [orders, setOrders] = useState<OrderListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionId, setActionId] = useState<string | null>(null);
  const [shipForm, setShipForm] = useState<{ orderId: string; carrier: string; tracking: string } | null>(
    null
  );

  const loadOrders = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const all = await ordersApi.listAsSeller();
      setOrders(
        all.filter((o) => FULFILMENT_STATUSES.includes(o.status))
      );
    } catch (err) {
      setError(extractMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user?.role !== "VENDOR") {
      navigate("/account", { replace: true });
      return;
    }
    loadOrders();
  }, [user, navigate, loadOrders]);

  const handleAcknowledge = async (orderId: string) => {
    setActionId(orderId);
    try {
      await ordersApi.acknowledge(orderId);
      await loadOrders();
    } catch (err) {
      alert(extractMessage(err));
    } finally {
      setActionId(null);
    }
  };

  const handleShip = async () => {
    if (!shipForm?.carrier.trim()) return;
    setActionId(shipForm.orderId);
    try {
      await ordersApi.ship(shipForm.orderId, {
        carrier: shipForm.carrier.trim(),
        tracking_number: shipForm.tracking.trim() || undefined,
      });
      setShipForm(null);
      await loadOrders();
    } catch (err) {
      alert(extractMessage(err));
    } finally {
      setActionId(null);
    }
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 space-y-5 sm:px-6 lg:px-8">
      <button onClick={() => navigate("/vendor")} className="text-sm text-gray-500 min-h-0">
        ← Vendor dashboard
      </button>
      <p className="text-sm font-bold tracking-[.16em] text-blue-600">FULFILMENT</p>
      <h1 className="text-4xl font-black tracking-tight text-slate-950">Orders to fulfil.</h1>
      <p className="text-sm text-gray-500">
        Acknowledge paid orders and mark them shipped when dispatched.
      </p>

      {loading && (
        <p className="text-center text-sm text-gray-500 py-12">Loading orders...</p>
      )}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {!loading && !error && orders.length === 0 && (
        <div className="card p-8 text-center text-sm text-gray-500">
          No orders awaiting fulfilment.
        </div>
      )}

      {orders.map((order) => (
        <article key={order.id} className="rounded-2xl border border-slate-200 bg-white p-5 space-y-3 shadow-sm">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="font-semibold text-gray-900">{order.reference}</p>
              <p className="text-xs text-gray-500">{formatDate(order.created_at)}</p>
            </div>
            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700">
              {order.status.replace(/_/g, " ")}
            </span>
          </div>
          <p className="text-sm text-gray-600">
            {order.item_count} item{order.item_count !== 1 ? "s" : ""} ·{" "}
            {formatZMW(order.total_zmw)}
          </p>
          <p className="text-xs text-gray-500">
            {STATUS_LABEL[order.status] ?? order.status}
          </p>

          <div className="flex flex-wrap gap-2">
            <Link
              to={`/orders/${order.id}`}
              className="rounded-lg border border-gray-200 px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50"
            >
              View details
            </Link>
            {order.status === "PAYMENT_RECEIVED" && (
              <button
                type="button"
                disabled={actionId === order.id}
                onClick={() => handleAcknowledge(order.id)}
                className="rounded-lg bg-blue-600 px-3 py-2 text-xs font-bold text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {actionId === order.id ? "Working..." : "Acknowledge order"}
              </button>
            )}
            {order.status === "PROCESSING" && (
              <button
                type="button"
                onClick={() =>
                  setShipForm({ orderId: order.id, carrier: "Zampost", tracking: "" })
                }
                className="rounded-lg bg-blue-600 px-3 py-2 text-xs font-bold text-white hover:bg-blue-700"
              >
                Mark shipped
              </button>
            )}
          </div>

          {shipForm?.orderId === order.id && (
            <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 space-y-2">
              <label className="block text-xs font-medium text-gray-700">
                Carrier
                <input
                  value={shipForm.carrier}
                  onChange={(e) =>
                    setShipForm({ ...shipForm, carrier: e.target.value })
                  }
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                />
              </label>
              <label className="block text-xs font-medium text-gray-700">
                Tracking number (optional)
                <input
                  value={shipForm.tracking}
                  onChange={(e) =>
                    setShipForm({ ...shipForm, tracking: e.target.value })
                  }
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                />
              </label>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={handleShip}
                  disabled={actionId === order.id}
                  className="rounded-lg bg-emerald-600 px-3 py-2 text-xs font-medium text-white"
                >
                  Confirm shipment
                </button>
                <button
                  type="button"
                  onClick={() => setShipForm(null)}
                  className="rounded-lg border border-gray-200 px-3 py-2 text-xs text-gray-600"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </article>
      ))}
    </div>
  );
};

export default VendorOrdersPage;
