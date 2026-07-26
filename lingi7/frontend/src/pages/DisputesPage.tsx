/**
 * DisputesPage — buyer dispute list (GET /api/v1/disputes/api/disputes/)
 */

import React from "react";
import { Link } from "react-router-dom";
import { useDisputes } from "../hooks";
import { formatDate } from "../utils";

const DisputesPage: React.FC = () => {
  const { disputes, isLoading, error } = useDisputes();

  if (isLoading) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 text-center text-sm text-gray-500">
        Loading disputes...
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 text-center">
        <p className="text-red-600">{error}</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
      <p className="text-sm font-bold tracking-[.16em] text-blue-600">BUYER PROTECTION</p>
      <h1 className="mb-6 mt-2 text-4xl font-black tracking-tight text-slate-950">My disputes.</h1>

      {disputes.length === 0 ? (
        <div className="card p-6 text-center text-sm text-gray-500">
          <p>You have no open disputes.</p>
          <Link to="/orders" className="mt-4 inline-block text-emerald-600 font-medium">
            View orders →
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {disputes.map((d) => (
            <div key={d.id} className="card p-4">
              <div className="flex justify-between items-start">
                <div>
                  <p className="text-xs font-mono text-gray-500">
                    {d.order_reference ?? `Dispute #${d.id}`}
                  </p>
                  <p className="mt-1 text-sm font-semibold text-gray-900">{d.reason}</p>
                  {d.description && (
                    <p className="mt-1 text-xs text-gray-500 line-clamp-2">{d.description}</p>
                  )}
                </div>
                <span className="rounded-full bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-800">
                  {d.status}
                </span>
              </div>
              <p className="mt-2 text-xs text-gray-400">{formatDate(d.created_at)}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default DisputesPage;
