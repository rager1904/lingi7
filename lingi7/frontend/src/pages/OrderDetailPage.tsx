/**
 * OrderDetailPage — full order view with escrow timeline, tracking, and dispute CTA
 */

import React, { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useOrder } from "../hooks";
import { EscrowStatusBadge } from "../components/escrow/EscrowStatusBadge";
import { ordersApi } from "../api/resources";
import {
  formatZMW,
  formatDateTime,
  formatDate,
  extractMessage,
  FULFILMENT_TYPE_LABEL,
  getOrderStatusLabel,
} from "../utils";

const OrderDetailPage: React.FC = () => {
  const { orderId } = useParams<{ orderId: string }>();
  const [searchParams] = useSearchParams();
  const justConfirmed = searchParams.get("confirmed") === "1";

  const id = orderId ?? null;
  const { order, isLoading, error, refresh } = useOrder(id);
  const shipment = order?.shipment ?? null;

  const [disputeOpen, setDisputeOpen] = useState(false);
  const [disputeReason, setDisputeReason] = useState("");
  const [disputeDesc, setDisputeDesc] = useState("");
  const [evidenceUrl, setEvidenceUrl] = useState("");
  const [disputeLoading, setDisputeLoading] = useState(false);
  const [disputeError, setDisputeError] = useState<string | null>(null);
  const [disputeSuccess, setDisputeSuccess] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [showCancel, setShowCancel] = useState(false);

  const handleRaiseDispute = async () => {
    if (!id || !disputeReason.trim() || disputeDesc.trim().length < 20) {
      setDisputeError("Description must be at least 20 characters.");
      return;
    }
    setDisputeLoading(true);
    setDisputeError(null);
    try {
      const urls = evidenceUrl.trim() ? [evidenceUrl.trim()] : [];
      await ordersApi.raiseDispute(id, disputeReason, disputeDesc, urls);
      setDisputeSuccess(true);
      setDisputeOpen(false);
      refresh();
    } catch (err) {
      setDisputeError(extractMessage(err));
    } finally {
      setDisputeLoading(false);
    }
  };

  const handleConfirmDelivery = async () => {
    if (!id) return;
    setActionLoading(true);
    try {
      await ordersApi.confirmDelivery(id);
      refresh();
    } catch (err) {
      alert(extractMessage(err));
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!id) return;
    setActionLoading(true);
    try {
      await ordersApi.cancel(id, cancelReason.trim());
      setShowCancel(false);
      refresh();
    } catch (err) {
      alert(extractMessage(err));
    } finally {
      setActionLoading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-8">
        <div className="animate-pulse space-y-4">
          <div className="h-8 w-56 rounded bg-gray-200" />
          <div className="h-40 rounded-xl bg-gray-100" />
          <div className="h-40 rounded-xl bg-gray-100" />
        </div>
      </div>
    );
  }

  if (error || !order) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 text-center">
        <p className="text-red-600">{error ?? "Order not found."}</p>
      </div>
    );
  }

  const canDispute =
    ["PAYMENT_RECEIVED", "PROCESSING", "SHIPPED", "DELIVERED"].includes(order.status) &&
    order.status !== "DISPUTED" &&
    !disputeSuccess;

  const canConfirmDelivery = order.status === "SHIPPED";
  const canCancel = ["DRAFT", "PENDING_PAYMENT"].includes(order.status);

  return (
    <div className="mx-auto max-w-2xl px-4 py-8 space-y-4">
      {/* Confirmation banner */}
      {justConfirmed && (
        <div className="rounded-xl border border-emerald-300 bg-emerald-50 p-4 text-sm text-emerald-800">
          <strong>Payment received!</strong> Your funds are held securely in
          escrow. The seller has been notified to fulfil your order.
        </div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-mono text-gray-500">{order.reference}</p>
          <h1 className="text-xl font-bold text-gray-900">
            Order Detail
          </h1>
          <p className="text-xs text-gray-500">{formatDateTime(order.created_at)}</p>
        </div>
        <EscrowStatusBadge status={order.escrow_status} />
      </div>

      {/* Escrow explanation */}
      <EscrowExplainer status={order.escrow_status} />

      {/* Order items */}
      <section className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <h2 className="mb-3 font-semibold text-gray-800">Items</h2>
        <div className="divide-y divide-gray-100">
          {order.items.map((item) => (
            <div key={item.id} className="flex items-center gap-3 py-3">
              {item.product_image_url && (
                <img
                  src={item.product_image_url}
                  alt={item.product_name}
                  className="h-12 w-12 rounded-lg object-cover"
                />
              )}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {item.product_name}
                </p>
                <p className="text-xs text-gray-500">
                  {formatZMW(item.unit_price_zmw)} × {item.quantity}
                </p>
              </div>
              <p className="text-sm font-semibold text-gray-900">
                {formatZMW(item.line_total_zmw)}
              </p>
            </div>
          ))}
        </div>
        <div className="mt-3 border-t border-gray-100 pt-3 space-y-1 text-sm">
          <div className="flex justify-between text-gray-600">
            <span>Subtotal</span>
            <span>{formatZMW(order.subtotal_zmw)}</span>
          </div>
          <div className="flex justify-between text-gray-600">
            <span>Platform fee</span>
            <span>{formatZMW(order.platform_fee_zmw)}</span>
          </div>
          <div className="flex justify-between font-bold text-gray-900 text-base pt-1">
            <span>Total</span>
            <span>{formatZMW(order.total_zmw)}</span>
          </div>
        </div>
      </section>

      {/* Fulfilment & notes */}
      <section className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm space-y-2 text-sm">
        <h2 className="font-semibold text-gray-800">Fulfilment</h2>
        <p className="text-gray-600">
          <span className="text-gray-500">Method: </span>
          {FULFILMENT_TYPE_LABEL[order.fulfilment_type ?? "STANDARD_DELIVERY"] ??
            order.fulfilment_type}
        </p>
        <p className="text-gray-600">
          <span className="text-gray-500">Order status: </span>
          {getOrderStatusLabel(order.status)}
        </p>
        {order.delivery_address && (
          <p className="text-gray-600">
            <span className="text-gray-500">Address: </span>
            {order.delivery_address}
          </p>
        )}
        {order.buyer_notes && (
          <p className="text-gray-600 border-t border-gray-100 pt-2">
            <span className="text-gray-500">Your notes: </span>
            {order.buyer_notes}
          </p>
        )}
      </section>

      {canConfirmDelivery && (
        <section className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
          <p className="text-sm text-emerald-800 mb-3">
            Has your order arrived? Confirm delivery to release escrow to the seller.
          </p>
          <button
            onClick={handleConfirmDelivery}
            disabled={actionLoading}
            className="btn-primary w-full py-2"
          >
            {actionLoading ? "Confirming..." : "Confirm Delivery"}
          </button>
        </section>
      )}

      {canCancel && (
        <section className="rounded-xl border border-gray-200 bg-white p-4">
          {!showCancel ? (
            <button
              onClick={() => setShowCancel(true)}
              className="text-sm text-red-600 font-medium"
            >
              Cancel order
            </button>
          ) : (
            <div className="space-y-2">
              <p className="text-sm font-medium text-gray-800">Cancel this order?</p>
              <textarea
                className="input"
                rows={2}
                placeholder="Reason (optional)"
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
              />
              <div className="flex gap-2">
                <button
                  onClick={() => setShowCancel(false)}
                  className="flex-1 rounded-lg border border-gray-300 py-2 text-sm"
                >
                  Keep order
                </button>
                <button
                  onClick={handleCancel}
                  disabled={actionLoading}
                  className="flex-1 rounded-lg bg-red-600 py-2 text-sm text-white"
                >
                  {actionLoading ? "Cancelling..." : "Confirm cancel"}
                </button>
              </div>
            </div>
          )}
        </section>
      )}

      {/* Shipment (orders app OrderShipment) */}
      {shipment && (
        <section className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="mb-3 font-semibold text-gray-800">Shipment</h2>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between gap-2">
              <dt className="text-gray-500">Carrier</dt>
              <dd className="font-medium text-gray-900">{shipment.carrier}</dd>
            </div>
            {shipment.tracking_number && (
              <div className="flex justify-between gap-2">
                <dt className="text-gray-500">Tracking #</dt>
                <dd className="font-mono text-xs text-gray-900">{shipment.tracking_number}</dd>
              </div>
            )}
            {shipment.tracking_url && (
              <a
                href={shipment.tracking_url}
                target="_blank"
                rel="noopener noreferrer"
                className="block text-center text-sm font-medium text-emerald-600 hover:underline"
              >
                Track on carrier site →
              </a>
            )}
            {shipment.shipped_at && (
              <p className="text-xs text-gray-500">
                Shipped {formatDateTime(shipment.shipped_at)}
              </p>
            )}
            {shipment.estimated_delivery && (
              <p className="text-xs text-gray-500">
                Estimated delivery: {formatDate(shipment.estimated_delivery)}
              </p>
            )}
          </dl>
        </section>
      )}

      {/* Dispute section */}
      {canDispute && !disputeSuccess && (
        <section className="rounded-xl border border-orange-200 bg-orange-50 p-4">
          {!disputeOpen ? (
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-orange-800">
                  Problem with your order?
                </p>
                <p className="text-xs text-orange-700">
                  Open a dispute and your funds stay protected in escrow.
                </p>
              </div>
              <button
                onClick={() => setDisputeOpen(true)}
                className="rounded-lg bg-orange-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-orange-700"
              >
                Open Dispute
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="font-medium text-orange-800">Open a Dispute</p>
              <div>
                <label className="mb-1 block text-xs font-medium text-orange-800">
                  Reason *
                </label>
                <select
                  value={disputeReason}
                  onChange={(e) => setDisputeReason(e.target.value)}
                  className="w-full rounded-lg border border-orange-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
                >
                  <option value="">Select a reason</option>
                  <option value="ITEM_NOT_RECEIVED">Item not delivered</option>
                  <option value="WRONG_ITEM">Wrong item received</option>
                  <option value="DAMAGED_ITEM">Item arrived damaged</option>
                  <option value="ITEM_NOT_AS_DESCRIBED">Not as described</option>
                  <option value="SELLER_UNRESPONSIVE">Seller unresponsive</option>
                  <option value="OTHER">Other</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-orange-800">
                  Description * (min 20 characters)
                </label>
                <textarea
                  value={disputeDesc}
                  onChange={(e) => setDisputeDesc(e.target.value)}
                  rows={3}
                  placeholder="Describe the issue in detail..."
                  className="w-full rounded-lg border border-orange-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-orange-800">
                  Evidence URL (optional)
                </label>
                <input
                  type="url"
                  value={evidenceUrl}
                  onChange={(e) => setEvidenceUrl(e.target.value)}
                  placeholder="https://..."
                  className="w-full rounded-lg border border-orange-300 bg-white px-3 py-2 text-sm"
                />
              </div>
              {disputeError && (
                <p className="text-xs text-red-600">{disputeError}</p>
              )}
              <div className="flex gap-2">
                <button
                  onClick={() => setDisputeOpen(false)}
                  className="flex-1 rounded-lg border border-orange-300 py-2 text-xs font-medium text-orange-700"
                >
                  Cancel
                </button>
                <button
                  onClick={handleRaiseDispute}
                  disabled={!disputeReason || disputeLoading}
                  className="flex-1 rounded-lg bg-orange-600 py-2 text-xs font-medium text-white hover:bg-orange-700 disabled:opacity-50"
                >
                  {disputeLoading ? "Submitting..." : "Submit Dispute"}
                </button>
              </div>
            </div>
          )}
        </section>
      )}

      {disputeSuccess && (
        <div className="rounded-xl border border-green-200 bg-green-50 p-4 text-sm text-green-800">
          Your dispute has been submitted. Your funds remain in escrow until
          it is resolved. Our team will contact you within 24 hours.
        </div>
      )}
    </div>
  );
};

const ESCROW_EXPLAIN: Partial<Record<string, string>> = {
  PENDING: "Awaiting your payment to secure the order.",
  HELD:
    "Your payment is held securely. The seller will now prepare your order.",
  IN_TRANSIT: "Your order is on its way. Funds release when delivery is confirmed.",
  DELIVERED:
    "Delivery confirmed. Funds will be released to the seller shortly.",
  RELEASED: "Transaction complete. Funds have been released to the seller.",
  DISPUTED: "A dispute is open. Funds are frozen until resolved.",
  FROZEN: "Your transaction is under review by our team.",
  REFUNDED: "A refund has been processed to your mobile money account.",
};

const EscrowExplainer: React.FC<{ status: string }> = ({ status }) => {
  const text = ESCROW_EXPLAIN[status];
  if (!text) return null;
  return (
    <p className="rounded-lg bg-gray-50 px-4 py-2 text-xs text-gray-600">
      🔒 {text}
    </p>
  );
};

export default OrderDetailPage;
