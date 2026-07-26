/**
 * CheckoutPage
 *
 * Flow:
 *   1. Review cart items + delivery address input
 *   2. Select MTN MoMo or Airtel Money
 *   3. Place order → initiate payment → poll status
 *   4. On SUCCESS: navigate to order confirmation
 *   5. On FAILED: show error, allow retry
 *
 * Escrow note: the backend creates the EscrowAccount at PENDING state
 * on order creation. The webhook moves it to HELD. Frontend only polls
 * payment status — it never writes to escrow directly.
 */

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCartStore } from "../store";
import { useAuth, usePaymentPoller } from "../hooks";
import { ordersApi, paymentsApi } from "../api/resources";
import {
  formatZMW,
  isValidZambianPhone,
  extractFieldErrors,
  extractMessage,
} from "../utils";
import type { PaymentProvider } from "../types";

type CheckoutStep = "review" | "payment" | "processing" | "error";

const DELIVERY_FEE_ZMW = 50; // flat MVP rate — phase 2 calculates dynamically

const CheckoutPage: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { items, totalZMW, clearCart } = useCartStore();

  const [step, setStep] = useState<CheckoutStep>("review");
  const [deliveryAddress, setDeliveryAddress] = useState("");
  const [provider, setProvider] = useState<PaymentProvider>("MTN");
  const [paymentPhone, setPaymentPhone] = useState(user?.phone_number ?? "");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [paymentId, setPaymentId] = useState<number | null>(null);
  const [orderId, setOrderId] = useState<number | null>(null);

  const { attempt, isPolling } = usePaymentPoller(paymentId);

  // Navigate to confirmation once payment succeeds
  React.useEffect(() => {
    if (attempt?.status === "SUCCESS" && orderId) {
      clearCart();
      navigate(`/orders/${orderId}?confirmed=1`);
    }
    if (attempt?.status === "FAILED") {
      setStep("error");
      setErrorMessage("Payment was not approved. Please try again.");
    }
  }, [attempt, orderId, clearCart, navigate]);

  if (items.length === 0 && step === "review") {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 text-center">
        <p className="text-gray-500">Your cart is empty.</p>
        <button
          onClick={() => navigate("/")}
          className="mt-4 rounded-lg bg-emerald-600 px-6 py-2 text-sm font-medium text-white hover:bg-emerald-700"
        >
          Continue Shopping
        </button>
      </div>
    );
  }

  const subtotal = parseFloat(totalZMW());
  const grandTotal = subtotal + DELIVERY_FEE_ZMW;

  const handlePlaceOrder = async () => {
    setFieldErrors({});
    setErrorMessage(null);

    if (!deliveryAddress.trim()) {
      setFieldErrors({ delivery_address: "Delivery address is required." });
      return;
    }
    if (!isValidZambianPhone(paymentPhone)) {
      setFieldErrors({ phone_number: "Enter a valid Zambian mobile number (+2609XXXXXXXX)." });
      return;
    }

    setStep("processing");

    try {
      const order = await ordersApi.place({
        items: items.map((i) => ({ product_id: i.product_id, quantity: i.quantity })),
        delivery_address: deliveryAddress,
        payment_provider: provider,
        phone_number: paymentPhone,
      });

      setOrderId(order.id);

      const payment = await paymentsApi.initiate({
        order_id: order.id,
        provider,
        phone_number: paymentPhone,
      });

      setPaymentId(payment.payment_id);
    } catch (err) {
      setFieldErrors(extractFieldErrors(err));
      setErrorMessage(extractMessage(err));
      setStep("error");
    }
  };

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Checkout</h1>

      {/* Progress indicator */}
      <div className="mb-8 flex items-center gap-2 text-sm">
        {(["review", "payment", "processing"] as CheckoutStep[]).map((s, idx) => (
          <React.Fragment key={s}>
            <span
              className={`rounded-full px-3 py-1 font-medium capitalize ${
                step === s
                  ? "bg-emerald-600 text-white"
                  : idx < ["review", "payment", "processing"].indexOf(step)
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-gray-100 text-gray-500"
              }`}
            >
              {s === "review" ? "Review" : s === "payment" ? "Payment" : "Processing"}
            </span>
            {idx < 2 && <span className="text-gray-300">→</span>}
          </React.Fragment>
        ))}
      </div>

      {/* ── Step 1: Review ── */}
      {step === "review" && (
        <div className="space-y-6">
          <OrderSummary items={items} subtotal={subtotal} deliveryFee={DELIVERY_FEE_ZMW} total={grandTotal} />

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Delivery Address *
            </label>
            <textarea
              value={deliveryAddress}
              onChange={(e) => setDeliveryAddress(e.target.value)}
              rows={3}
              placeholder="House/plot number, area, city (e.g. Plot 47 Kabulonga, Lusaka)"
              className={`w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 ${
                fieldErrors.delivery_address ? "border-red-400" : "border-gray-300"
              }`}
            />
            {fieldErrors.delivery_address && (
              <p className="mt-1 text-xs text-red-600">{fieldErrors.delivery_address}</p>
            )}
          </div>

          <button
            onClick={() => setStep("payment")}
            disabled={!deliveryAddress.trim()}
            className="w-full rounded-lg bg-emerald-600 py-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            Continue to Payment
          </button>
        </div>
      )}

      {/* ── Step 2: Payment ── */}
      {step === "payment" && (
        <div className="space-y-6">
          <OrderSummary items={items} subtotal={subtotal} deliveryFee={DELIVERY_FEE_ZMW} total={grandTotal} compact />

          <EscrowNotice total={grandTotal} />

          <div>
            <p className="mb-3 text-sm font-medium text-gray-700">
              Select Payment Method
            </p>
            <div className="grid grid-cols-2 gap-3">
              {(["MTN", "AIRTEL"] as PaymentProvider[]).map((p) => (
                <ProviderCard
                  key={p}
                  provider={p}
                  selected={provider === p}
                  onSelect={() => setProvider(p)}
                />
              ))}
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              {provider === "MTN" ? "MTN MoMo" : "Airtel Money"} Number *
            </label>
            <input
              type="tel"
              value={paymentPhone}
              onChange={(e) => setPaymentPhone(e.target.value)}
              placeholder="+260971234567"
              className={`w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 ${
                fieldErrors.phone_number ? "border-red-400" : "border-gray-300"
              }`}
            />
            {fieldErrors.phone_number && (
              <p className="mt-1 text-xs text-red-600">{fieldErrors.phone_number}</p>
            )}
            <p className="mt-1 text-xs text-gray-500">
              You will receive a USSD prompt to approve the payment.
            </p>
          </div>

          <div className="flex gap-3">
            <button
              onClick={() => setStep("review")}
              className="flex-1 rounded-lg border border-gray-300 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Back
            </button>
            <button
              onClick={handlePlaceOrder}
              className="flex-1 rounded-lg bg-emerald-600 py-3 text-sm font-semibold text-white hover:bg-emerald-700"
            >
              Pay {formatZMW(grandTotal)}
            </button>
          </div>
        </div>
      )}

      {/* ── Step 3: Processing ── */}
      {step === "processing" && (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-center shadow-sm">
          <div className="mx-auto mb-4 h-12 w-12 animate-spin rounded-full border-4 border-emerald-200 border-t-emerald-600" />
          <h2 className="mb-2 text-lg font-semibold text-gray-900">
            Waiting for Payment Approval
          </h2>
          <p className="text-sm text-gray-500">
            {isPolling
              ? `Check your phone for a ${provider === "MTN" ? "MTN MoMo" : "Airtel Money"} USSD prompt and enter your PIN to approve.`
              : "Initiating payment request..."}
          </p>
          <p className="mt-4 text-xs text-gray-400">
            Your funds will be held securely in escrow until delivery is confirmed.
          </p>
        </div>
      )}

      {/* ── Error state ── */}
      {step === "error" && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-6">
          <h2 className="mb-2 font-semibold text-red-800">Payment Failed</h2>
          <p className="mb-4 text-sm text-red-700">
            {errorMessage ?? "Something went wrong. Please try again."}
          </p>
          <button
            onClick={() => {
              setStep("payment");
              setErrorMessage(null);
              setPaymentId(null);
            }}
            className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
          >
            Try Again
          </button>
        </div>
      )}
    </div>
  );
};

// ── Sub-components ────────────────────────────────────────────────────────────

interface SummaryProps {
  items: ReturnType<typeof useCartStore>["items"];
  subtotal: number;
  deliveryFee: number;
  total: number;
  compact?: boolean;
}

const OrderSummary: React.FC<SummaryProps> = ({
  items,
  subtotal,
  deliveryFee,
  total,
  compact,
}) => (
  <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
    <h2 className="mb-3 font-semibold text-gray-800">
      {compact ? "Order Summary" : `Your Cart (${items.length} item${items.length !== 1 ? "s" : ""})`}
    </h2>
    {!compact &&
      items.map((item) => (
        <div key={item.product_id} className="flex items-center justify-between py-2 text-sm">
          <span className="text-gray-700">
            {item.product_name} × {item.quantity}
          </span>
          <span className="font-medium text-gray-900">
            {formatZMW(parseFloat(item.price_zmw) * item.quantity)}
          </span>
        </div>
      ))}
    <div className="mt-2 border-t border-gray-100 pt-2 space-y-1 text-sm">
      <div className="flex justify-between text-gray-600">
        <span>Subtotal</span>
        <span>{formatZMW(subtotal)}</span>
      </div>
      <div className="flex justify-between text-gray-600">
        <span>Delivery</span>
        <span>{formatZMW(deliveryFee)}</span>
      </div>
      <div className="flex justify-between font-semibold text-gray-900 text-base pt-1 border-t border-gray-100">
        <span>Total</span>
        <span>{formatZMW(total)}</span>
      </div>
    </div>
  </div>
);

const EscrowNotice: React.FC<{ total: number }> = ({ total }) => (
  <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
    <span className="font-semibold">🔒 Secure Escrow:</span> Your payment of{" "}
    {formatZMW(total)} will be held safely until you confirm delivery. You are
    protected against non-delivery.
  </div>
);

const ProviderCard: React.FC<{
  provider: PaymentProvider;
  selected: boolean;
  onSelect: () => void;
}> = ({ provider, selected, onSelect }) => (
  <button
    onClick={onSelect}
    className={`flex flex-col items-center gap-2 rounded-xl border-2 p-4 text-sm font-medium transition-colors ${
      selected
        ? "border-emerald-500 bg-emerald-50 text-emerald-800"
        : "border-gray-200 bg-white text-gray-700 hover:border-gray-300"
    }`}
  >
    <span className="text-2xl">{provider === "MTN" ? "🟡" : "🔴"}</span>
    <span>{provider === "MTN" ? "MTN MoMo" : "Airtel Money"}</span>
  </button>
);

export default CheckoutPage;
