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
  UNVERIFIED: {
    label: "Not Submitted",
    colour: "bg-gray-100 text-gray-600",
    description: "Submit your NRC to unlock full platform access and higher limits.",
    canResubmit: true,
  },
  PENDING: {
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

  if (!user) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 text-center text-sm text-gray-500">
        Loading account...
      </div>
    );
  }

  const kyc =
    KYC_CONFIG[user.kyc_status] ??
    KYC_CONFIG.UNVERIFIED;

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 space-y-5 sm:px-6">
      <p className="text-sm font-bold tracking-[.16em] text-blue-600">ACCOUNT</p>
      <h1 className="text-4xl font-black tracking-tight text-slate-950">Your Lingi7 space.</h1>

      {user.is_frozen && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          Your account is frozen. Contact{" "}
          <a href="mailto:support@lingi7.com" className="font-medium underline">
            support@lingi7.com
          </a>{" "}
          for assistance.
        </div>
      )}

      {/* ── Profile card ── */}
      <section className="rounded-3xl bg-slate-950 p-6 text-white shadow-xl">
        <div className="flex items-center gap-4">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-blue-500 text-xl font-bold text-white select-none">
            {user.full_name.charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0">
            <p className="font-semibold text-white truncate">{user.full_name}</p>
            <p className="text-sm text-slate-300">{formatPhone(user.phone_number)}</p>
            {user.email && (
              <p className="text-sm text-slate-300 truncate">{user.email}</p>
            )}
            <p className="mt-1 text-xs text-slate-400">
              Member since {formatDate(user.date_joined)}
            </p>
          </div>
        </div>
        <div className="mt-3">
          <span className="rounded-full bg-white/10 px-2.5 py-0.5 text-xs font-medium text-blue-200 capitalize">
            {user.role.toLowerCase()}
          </span>
        </div>
      </section>

      {/* ── KYC status ── */}
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
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
      <section className="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        {[
          { label: "My Orders", icon: "📦", path: "/orders" },
          { label: "My Disputes", icon: "⚖️", path: "/disputes" },
          { label: "Edit Profile", icon: "✏️", path: "/account/profile" },
          ...(user.role === "VENDOR"
            ? [{ label: "Vendor Dashboard", icon: "🏪", path: "/vendor" }]
            : []),
          ...(kyc.canResubmit
            ? [{ label: "Submit KYC", icon: "🪪", path: "/account/kyc" }]
            : []),
        ].map(({ label, icon, path }) => (
          <button
            key={label}
            onClick={() => navigate(path)}
            className="flex w-full items-center justify-between px-5 py-4 text-sm text-slate-700 hover:bg-blue-50 min-h-0"
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
