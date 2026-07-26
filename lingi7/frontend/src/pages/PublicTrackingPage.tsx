/**
 * PublicTrackingPage — accessible via /track/:token, no auth required
 */

import React from "react";
import { useParams } from "react-router-dom";
import { useTrackingByToken } from "../hooks";
import { TrackingTimeline } from "../components/tracking/TrackingTimeline";
import { formatDate, formatDateTime, SHIPMENT_STATUS_LABEL } from "../utils";

export const PublicTrackingPage: React.FC = () => {
  const { token } = useParams<{ token: string }>();
  const { shipment, isLoading, error } = useTrackingByToken(token ?? null);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 text-center">
        <div className="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-emerald-200 border-t-emerald-600" />
        <p className="mt-4 text-sm text-gray-500">Loading shipment info...</p>
      </div>
    );
  }

  if (error || !shipment) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 text-center">
        <p className="text-gray-500">
          {error ?? "Tracking information not found. Check your tracking link."}
        </p>
      </div>
    );
  }

  const statusLabel =
    shipment.status_display ?? SHIPMENT_STATUS_LABEL[shipment.status] ?? shipment.status;

  return (
    <div className="mx-auto max-w-lg px-4 py-8 sm:px-6">
      <div className="mb-6 flex items-center gap-2">
        <span className="text-2xl font-black text-slate-950">LINGI<span className="text-blue-600">7</span></span>
        <span className="text-sm text-gray-500">Shipment Tracking</span>
      </div>

      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="mb-4 flex items-start justify-between">
          <div>
            <p className="text-xs text-gray-500">Current status</p>
            <p className="text-lg font-bold text-gray-900">{statusLabel}</p>
          </div>
          {shipment.carrier_name && (
            <div className="text-right">
              <p className="text-xs text-gray-500">Carrier</p>
              <p className="text-sm font-medium text-gray-700">{shipment.carrier_name}</p>
              {shipment.tracking_number && (
                <p className="text-xs font-mono text-gray-500">{shipment.tracking_number}</p>
              )}
            </div>
          )}
        </div>

        {(shipment.origin_country || shipment.destination_country) && (
          <p className="mb-3 text-sm text-gray-600">
            Route:{" "}
            <strong>
              {shipment.origin_country ?? "?"} → {shipment.destination_country ?? "?"}
            </strong>
          </p>
        )}

        {shipment.shipping_method_display && (
          <p className="mb-3 text-sm text-gray-600">
            Shipping: <strong>{shipment.shipping_method_display}</strong>
          </p>
        )}

        {shipment.estimated_delivery && (
          <div className="mb-4 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
            Estimated delivery: <strong>{formatDate(shipment.estimated_delivery)}</strong>
          </div>
        )}

        {shipment.delivered_at && (
          <p className="mb-4 text-sm text-gray-600">
            Delivered {formatDateTime(shipment.delivered_at)}
          </p>
        )}

        <TrackingTimeline events={shipment.events} currentStatus={shipment.status} />
      </div>

      <p className="mt-4 text-center text-xs text-gray-400">
        Powered by Lingi7 · Secure Escrow Commerce
      </p>
    </div>
  );
};

export default PublicTrackingPage;
