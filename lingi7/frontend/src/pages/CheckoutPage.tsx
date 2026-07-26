/**
 * CheckoutPage
 *
 * Flow:
 *   1. Review cart items + delivery address input
 *   2. Select MTN MoMo or Airtel Money
 *   3. Place order → initiate payment → poll status
 *   4. On SUCCESS: navigate to order confirmation
 *   5. On FAILED: allow retry (reuses existing order — no duplicates)
 */

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCartStore, type CartItem } from "../store";
import { useAuth, usePaymentPoller } from "../hooks";
import { ordersApi, paymentsApi } from "../api/resources";
import { PhoneInput } from "../components/forms/PhoneInput";
import {
  formatZMW,
  isValidZambianPhone,
  normalizeZambianPhone,
  extractFieldErrors,
  extractMessage,
} from "../utils";
import type { FulfilmentType, PaymentProvider } from "../types";
import { FULFILMENT_TYPE_LABEL } from "../utils";

type CheckoutStep = "review" | "payment" | "processing" | "error";

interface OrderTotals {
  subtotal: number;
  platformFee: number;
  total: number;
}

const CheckoutPage: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { items, totalZMW, clearCart, removeItem, updateQuantity, sellerSwitchNotice, clearSellerSwitchNotice } =
    useCartStore();

  const [step, setStep] = useState<CheckoutStep>("review");
  const [fulfilmentType, setFulfilmentType] = useState<FulfilmentType>("STANDARD_DELIVERY");
  const [deliveryAddress, setDeliveryAddress] = useState("");
  const [buyerNotes, setBuyerNotes] = useState("");
  const [provider, setProvider] = useState<PaymentProvider>("MTN");
  const [paymentPhone, setPaymentPhone] = useState(
    user?.phone_number ? normalizeZambianPhone(user.phone_number) : "+260"
  );
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [paymentId, setPaymentId] = useState<string | null>(null);
  const [orderId, setOrderId] = useState<string | null>(null);
  const [orderTotals, setOrderTotals] = useState<OrderTotals | null>(null);

  const { attempt, isPolling } = usePaymentPoller(paymentId, {
    onTerminalFailure: (msg) => {
      setStep("error");
      setErrorMessage(msg);
    },
  });

  React.useEffect(() => {
    if (attempt?.status === "SUCCESS" && orderId) {
      clearCart();
      navigate(`/orders/${orderId}?confirmed=1`);
    }
    if (attempt?.status === "FAILED" || attempt?.status === "CANCELLED") {
      setStep("error");
      setErrorMessage(
        attempt.status === "CANCELLED"
          ? "Payment was cancelled. You can try again."
          : "Payment was not approved. Please try again."
      );
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

  const cartSubtotal = parseFloat(totalZMW());
  const displayTotals: OrderTotals = orderTotals ?? {
    subtotal: cartSubtotal,
    platformFee: 0,
    total: cartSubtotal,
  };

  const needsDeliveryAddress = fulfilmentType === "STANDARD_DELIVERY";
  const canContinueReview =
    !needsDeliveryAddress || deliveryAddress.trim().length > 0;

  const kycBlocked = user && user.kyc_status !== "VERIFIED";
  const frozenBlocked = user?.is_frozen === true || user?.is_active === false;

  const ensureOrder = async (): Promise<string> => {
    if (orderId) return orderId;

    const seller_id = items[0]?.seller_id;
    if (!seller_id) {
      throw new Error("Missing seller information. Remove items and add again.");
    }

    const draft = await ordersApi.create({
      seller_id,
      lines: items.map((i) => ({
        product_id: i.product_id,
        quantity: i.quantity,
      })),
      fulfilment_type: fulfilmentType,
      delivery_address: needsDeliveryAddress ? deliveryAddress.trim() : "",
      buyer_notes: buyerNotes.trim() || undefined,
    });

    const order = await ordersApi.submit(draft.id);
    setOrderId(order.id);
    setOrderTotals({
      subtotal: parseFloat(order.subtotal_zmw),
      platformFee: parseFloat(order.platform_fee_zmw),
      total: parseFloat(order.total_zmw),
    });
    return order.id;
  };

  const handlePlaceOrder = async () => {
    setFieldErrors({});
    setErrorMessage(null);

    if (needsDeliveryAddress && !deliveryAddress.trim()) {
      setFieldErrors({ delivery_address: "Delivery address is required for standard delivery." });
      return;
    }
    if (!isValidZambianPhone(paymentPhone)) {
      setFieldErrors({ phone_number: "Enter a valid MTN, Airtel, or Zamtel mobile number." });
      return;
    }

    setStep("processing");

    try {
      const id = await ensureOrder();
      const payment = await paymentsApi.initiate({
        order_id: id,
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

  const handleRetryPayment = async () => {
    setErrorMessage(null);
    if (!orderId) {
      setStep("payment");
      return;
    }
    setStep("processing");
    setPaymentId(null);
    try {
      const payment = await paymentsApi.initiate({
        order_id: orderId,
        provider,
        phone_number: paymentPhone,
      });
      setPaymentId(payment.payment_id);
    } catch (err) {
      setErrorMessage(extractMessage(err));
      setStep("error");
    }
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-8"><p className="text-sm font-bold tracking-[.16em] text-blue-600">SECURE CHECKOUT</p><h1 className="mt-2 text-4xl font-black tracking-tight text-slate-950">Almost yours.</h1><p className="mt-2 text-sm text-slate-500">Your payment stays protected in escrow until delivery is confirmed.</p></div>

      {sellerSwitchNotice && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 flex justify-between gap-2">
          <span>{sellerSwitchNotice}</span>
          <button type="button" onClick={clearSellerSwitchNotice} className="text-amber-700 underline shrink-0">
            Dismiss
          </button>
        </div>
      )}

      {(kycBlocked || frozenBlocked) && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {frozenBlocked ? (
            <p>
              Your account is frozen. Contact{" "}
              <a href="mailto:support@lingi7.com" className="underline">
                support@lingi7.com
              </a>{" "}
              before placing orders.
            </p>
          ) : (
            <p>
              Identity verification is required before checkout.{" "}
              <button
                type="button"
                onClick={() => navigate("/account/kyc")}
                className="font-medium underline"
              >
                Complete KYC
              </button>
            </p>
          )}
        </div>
      )}

      <div className="mb-8 flex items-center gap-2 text-sm">
        {(["review", "payment", "processing"] as CheckoutStep[]).map((s, idx) => (
          <React.Fragment key={s}>
            <span
              className={`rounded-full px-3 py-1 font-medium capitalize ${
                step === s
                  ? "bg-blue-600 text-white"
                  : idx < ["review", "payment", "processing"].indexOf(step)
                  ? "bg-blue-100 text-blue-700"
                  : "bg-gray-100 text-gray-500"
              }`}
            >
              {s === "review" ? "Review" : s === "payment" ? "Payment" : "Processing"}
            </span>
            {idx < 2 && <span className="text-gray-300">→</span>}
          </React.Fragment>
        ))}
      </div>

      {step === "review" && (
        <div className="grid gap-7 lg:grid-cols-[1fr_.75fr]">
          <div className="space-y-6">
          <OrderSummary
            items={items}
            subtotal={displayTotals.subtotal}
            platformFee={displayTotals.platformFee}
            total={displayTotals.total}
            showFeeNote={!orderTotals}
            editable
            onRemove={removeItem}
            onUpdateQuantity={updateQuantity}
          />

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Fulfilment method *
            </label>
            <select
              className="input"
              value={fulfilmentType}
              onChange={(e) => setFulfilmentType(e.target.value as FulfilmentType)}
            >
              {Object.entries(FULFILMENT_TYPE_LABEL).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          {needsDeliveryAddress && (
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Delivery address *
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
          )}

          {fulfilmentType === "PICKUP" && (
            <p className="rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-800">
              You will collect this order from the seller. They will contact you with pickup details.
            </p>
          )}

          {fulfilmentType === "DIGITAL" && (
            <p className="rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-800">
              Digital goods are delivered electronically after payment is confirmed.
            </p>
          )}

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Order notes
            </label>
            <textarea
              value={buyerNotes}
              onChange={(e) => setBuyerNotes(e.target.value)}
              rows={2}
              placeholder="Optional instructions for the seller (size, colour, delivery time...)"
              className="input"
            />
          </div>

          <button
            onClick={() => setStep("payment")}
            disabled={!canContinueReview || !!kycBlocked || !!frozenBlocked}
            className="w-full rounded-xl bg-blue-600 py-3.5 text-sm font-bold text-white shadow-lg shadow-blue-600/20 hover:bg-blue-700 disabled:opacity-50"
          >
            Continue to Payment
          </button>
          </div><aside className="h-fit rounded-2xl bg-slate-950 p-6 text-white"><p className="text-sm font-bold tracking-[.14em] text-cyan-300">SAFE BY DESIGN</p><h2 className="mt-3 text-xl font-black">Your money is protected.</h2><p className="mt-3 text-sm leading-6 text-slate-300">Every eligible payment remains in escrow until you confirm the order is right.</p><div className="mt-5 space-y-3 text-sm text-slate-200"><p>◈ Secure mobile money</p><p>◈ Delivery confirmation</p><p>◈ Dispute resolution</p></div></aside></div>
      )}

      {step === "payment" && (
        <div className="mx-auto max-w-2xl space-y-6">
          <OrderSummary
            items={items}
            subtotal={displayTotals.subtotal}
            platformFee={displayTotals.platformFee}
            total={displayTotals.total}
            compact
            showFeeNote={!orderTotals}
          />

          <EscrowNotice total={displayTotals.total || cartSubtotal} />

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
            <PhoneInput
              value={paymentPhone}
              onChange={setPaymentPhone}
              error={fieldErrors.phone_number}
              hint="You will receive a USSD prompt to approve the payment."
            />
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
              disabled={!!kycBlocked || !!frozenBlocked}
              className="flex-1 rounded-lg bg-emerald-600 py-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              Pay {formatZMW(orderTotals ? displayTotals.total : cartSubtotal)}
              {!orderTotals && "+"}
            </button>
          </div>
        </div>
      )}

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
          {orderTotals && (
            <p className="mt-3 text-sm font-medium text-gray-800">
              Amount: {formatZMW(orderTotals.total)}
            </p>
          )}
          <p className="mt-4 text-xs text-gray-400">
            Your funds will be held securely in escrow until delivery is confirmed.
          </p>
        </div>
      )}

      {step === "error" && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-6">
          <h2 className="mb-2 font-semibold text-red-800">Payment Failed</h2>
          <p className="mb-4 text-sm text-red-700">
            {errorMessage ?? "Something went wrong. Please try again."}
          </p>
          <button
            onClick={handleRetryPayment}
            className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
          >
            Try Again
          </button>
        </div>
      )}
    </div>
  );
};

interface SummaryProps {
  items: CartItem[];
  subtotal: number;
  platformFee: number;
  total: number;
  compact?: boolean;
  showFeeNote?: boolean;
  editable?: boolean;
  onRemove?: (productId: number) => void;
  onUpdateQuantity?: (productId: number, quantity: number) => void;
}

const OrderSummary: React.FC<SummaryProps> = ({
  items,
  subtotal,
  platformFee,
  total,
  compact,
  showFeeNote,
  editable,
  onRemove,
  onUpdateQuantity,
}) => (
  <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
    <h2 className="mb-3 font-semibold text-gray-800">
      {compact ? "Order Summary" : `Your Cart (${items.length} item${items.length !== 1 ? "s" : ""})`}
    </h2>
    {!compact &&
      items.map((item) => (
        <div key={item.product_id} className="flex items-center justify-between gap-2 py-2 text-sm border-b border-gray-50 last:border-0">
          <div className="min-w-0 flex-1">
            <p className="text-gray-700 truncate">{item.product_name}</p>
            {editable && onUpdateQuantity ? (
              <div className="mt-1 flex items-center gap-2">
                <button
                  type="button"
                  aria-label="Decrease quantity"
                  className="h-7 w-7 rounded border border-gray-300 text-gray-600"
                  onClick={() => onUpdateQuantity(item.product_id, item.quantity - 1)}
                >
                  −
                </button>
                <span className="text-xs text-gray-600">{item.quantity}</span>
                <button
                  type="button"
                  aria-label="Increase quantity"
                  className="h-7 w-7 rounded border border-gray-300 text-gray-600 disabled:opacity-40"
                  disabled={item.quantity >= item.max_stock}
                  onClick={() => onUpdateQuantity(item.product_id, item.quantity + 1)}
                >
                  +
                </button>
                {onRemove && (
                  <button
                    type="button"
                    onClick={() => onRemove(item.product_id)}
                    className="text-xs text-red-600 hover:underline ml-1"
                  >
                    Remove
                  </button>
                )}
              </div>
            ) : (
              <span className="text-xs text-gray-500">× {item.quantity}</span>
            )}
          </div>
          <span className="font-medium text-gray-900 shrink-0">
            {formatZMW(parseFloat(item.price_zmw) * item.quantity)}
          </span>
        </div>
      ))}
    <div className="mt-2 border-t border-gray-100 pt-2 space-y-1 text-sm">
      <div className="flex justify-between text-gray-600">
        <span>Subtotal</span>
        <span>{formatZMW(subtotal)}</span>
      </div>
      {platformFee > 0 ? (
        <div className="flex justify-between text-gray-600">
          <span>Platform fee</span>
          <span>{formatZMW(platformFee)}</span>
        </div>
      ) : showFeeNote ? (
        <p className="text-xs text-gray-500">Platform fee calculated when you pay.</p>
      ) : null}
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
