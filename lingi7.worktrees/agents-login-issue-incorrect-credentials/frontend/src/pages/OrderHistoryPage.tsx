/**
 * OrderHistoryPage — paginated list of buyer's orders
 */

import React from "react";
import { Link } from "react-router-dom";
import { useOrders } from "../hooks";
import { EscrowStatusBadge } from "../components/escrow/EscrowStatusBadge";
import { formatZMW, formatDate, ORDER_STATUS_LABEL } from "../utils";

const OrderHistoryPage: React.FC = () => {
  const { orders, isLoading, error, hasMore, loadMore } = useOrders();

  if (isLoading && orders.length === 0) {
    return <PageSkeleton />;
  }

  if (error) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 text-center">
        <p className="text-red-600">{error}</p>
      </div>
    );
  }

  if (orders.length === 0) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 text-center">
        <p className="text-gray-500">You haven't placed any orders yet.</p>
        <Link
          to="/"
          className="mt-4 inline-block rounded-lg bg-emerald-600 px-6 py-2 text-sm font-medium text-white hover:bg-emerald-700"
        >
          Start Shopping
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">My Orders</h1>

      <div className="space-y-3">
        {orders.map((order) => (
          <Link
            key={order.id}
            to={`/orders/${order.id}`}
            className="block rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition hover:shadow-md"
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-mono text-gray-500">{order.reference}</p>
                <p className="mt-0.5 text-sm font-semibold text-gray-900">
                  {order.item_count} item{order.item_count !== 1 ? "s" : ""}
                </p>
                <p className="mt-0.5 text-xs text-gray-500">{formatDate(order.created_at)}</p>
              </div>
              <div className="flex flex-col items-end gap-2">
                <span className="text-base font-bold text-gray-900">
                  {formatZMW(order.total_zmw)}
                </span>
                <EscrowStatusBadge status={order.escrow_status} size="sm" />
              </div>
            </div>
            <div className="mt-3 flex items-center justify-between border-t border-gray-100 pt-3">
              <span className="text-xs text-gray-500">
                Order: {ORDER_STATUS_LABEL[order.status]}
              </span>
              <span className="text-xs font-medium text-emerald-600">View Details →</span>
            </div>
          </Link>
        ))}
      </div>

      {hasMore && (
        <button
          onClick={loadMore}
          disabled={isLoading}
          className="mt-6 w-full rounded-lg border border-gray-300 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          {isLoading ? "Loading..." : "Load More Orders"}
        </button>
      )}
    </div>
  );
};

const PageSkeleton: React.FC = () => (
  <div className="mx-auto max-w-2xl px-4 py-8">
    <div className="mb-6 h-8 w-40 animate-pulse rounded bg-gray-200" />
    {[1, 2, 3].map((i) => (
      <div key={i} className="mb-3 h-24 animate-pulse rounded-xl bg-gray-100" />
    ))}
  </div>
);

export default OrderHistoryPage;
