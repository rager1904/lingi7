/**
 * AccountPage — profile overview, KYC status, quick links, logout
 */

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks";
import { formatDate, formatPhone } from "../utils";
import type { KYCStatus } from "../types";

const KYC_CONFIG: Record<
  KYCStatus,
  { label: string; colour: string; description: string; canResubmit: boolean }
> = {
  PENDING: {
    label: "Not Submitted",
    colour: "bg-gray-100 text-gray-600",
    description: "Submit your NRC to unlock full platform access and higher limits.",
    canResubmit: true,
  },
  SUBMITTED: {
    label: "Under Review",
    colour: "bg-yellow-100 text-yellow-800",
    description: "Documents received. Review usually takes 24–48 hours.",
    canResubmit: false,
  },
  VERIFIED: {
    label: "Verified ✓",
    colour: "bg-green-100 text-green-800",
    description: "Identity verified. Full platform access enabled.",
    canResubmit: false,
  },
  REJECTED: {
    label: "Rejected",
    colour: "bg-red-100 text-red-800",
    description: "Documents rejected. Please resubmit with clear, unobstructed photos.",
    canResubmit: true,
  },
};

const AccountPage: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [loggingOut, setLoggingOut] = useState(false);

  const handleLogout = async () => {
    setLoggingOut(true);
    await logout();
    navigate("/login", { replace: true });
  };

  if (!user) return null;

  const kyc = KYC_CONFIG[user.kyc_status];

  return (
    <div className="mx-auto max-w-lg px-4 py-6 space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">My Account</h1>

      {/* ── Profile card ── */}
      <section className="card p-5">
        <div className="flex items-center gap-4">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-xl font-bold text-emerald-700 select-none">
            {user.full_name.charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0">
            <p className="font-semibold text-gray-900 truncate">{user.full_name}</p>
            <p className="text-sm text-gray-500">{formatPhone(user.phone_number)}</p>
            {user.email && (
              <p className="text-sm text-gray-500 truncate">{user.email}</p>
            )}
            <p className="mt-1 text-xs text-gray-400">
              Member since {formatDate(user.date_joined)}
            </p>
          </div>
        </div>
        <div className="mt-3">
          <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-700 capitalize">
            {user.role.toLowerCase()}
          </span>
        </div>
      </section>

      {/* ── KYC status ── */}
      <section className="card p-5">
        <div className="flex items-start justify-between gap-2">
          <h2 className="font-semibold text-gray-800">Identity Verification (KYC)</h2>
          <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${kyc.colour}`}>
            {kyc.label}
          </span>
        </div>
        <p className="mt-2 text-sm text-gray-600">{kyc.description}</p>
        {kyc.canResubmit && (
          <button
            onClick={() => navigate("/account/kyc")}
            className="btn-primary mt-3"
          >
            Submit Documents
          </button>
        )}
      </section>

      {/* ── Quick links ── */}
      <section className="card divide-y divide-gray-100 overflow-hidden">
        {[
          { label: "My Orders", icon: "📦", path: "/orders" },
          { label: "Shipment Tracking", icon: "🚚", path: "/orders" },
          { label: "Help & Support", icon: "💬", path: "/support" },
        ].map(({ label, icon, path }) => (
          <button
            key={label}
            onClick={() => navigate(path)}
            className="flex w-full items-center justify-between px-5 py-3.5 text-sm text-gray-700 hover:bg-gray-50 min-h-0"
          >
            <span className="flex items-center gap-3">
              <span aria-hidden>{icon}</span>
              {label}
            </span>
            <span className="text-gray-400" aria-hidden>→</span>
          </button>
        ))}
      </section>

      {/* ── Regulatory footer ── */}
      <p className="text-center text-xs text-gray-400 leading-relaxed">
        Your data is protected under the Zambia Data Protection Act 2021.
        <br />
        AfriCore Intelligence Limited · PACRA Registered · Lusaka
      </p>

      {/* ── Logout ── */}
      <button
        onClick={handleLogout}
        disabled={loggingOut}
        className="w-full rounded-xl border border-red-200 py-3 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 transition-colors min-h-0"
      >
        {loggingOut ? "Signing out..." : "Sign Out"}
      </button>
    </div>
  );
};

export default AccountPage;
