/**
 * AuthPages — Login and Register pages
 * Split into named exports; lazy-loaded via dynamic import in App.tsx
 */

import React, { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { authApi } from "../api/auth";
import { useAuth } from "../hooks";
import { PhoneInput } from "../components/forms/PhoneInput";
import {
  isValidZambianPhone,
  extractFieldErrors,
  extractMessage,
} from "../utils";
import type { RegisterPayload } from "../types";

// ─── Shared FormField ─────────────────────────────────────────────────────────

interface FieldProps {
  label: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  error?: string;
  autoComplete?: string;
}

const FormField: React.FC<FieldProps> = ({
  label,
  type = "text",
  value,
  onChange,
  placeholder,
  error,
  autoComplete,
}) => (
  <div>
    <label className="mb-1 block text-sm font-medium text-gray-700">
      {label}
    </label>
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      autoComplete={autoComplete}
      className={`input ${error ? "input-error" : ""}`}
    />
    {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
  </div>
);

// ─── LoginPage ────────────────────────────────────────────────────────────────

export const LoginPage: React.FC = () => {
  const { login, isLoading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string })?.from ?? "/";

  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const handleSubmit = async () => {
    setError(null);
    setFieldErrors({});

    const errs: Record<string, string> = {};
    if (!isValidZambianPhone(phone)) {
      errs.phone = "Enter a valid MTN, Airtel, or Zamtel mobile number.";
    }
    if (!password) errs.password = "Password is required.";
    if (Object.keys(errs).length) { setFieldErrors(errs); return; }

    try {
      await login(phone, password);
      navigate(from, { replace: true });
    } catch (err) {
      const msg = extractMessage(err);
      setError(
        msg && msg !== "Request failed"
          ? msg
          : "Incorrect phone number or password."
      );
    }
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSubmit();
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm">
        {/* Brand */}
        <div className="mb-8 text-center">
          <h1 className="text-4xl font-black text-emerald-600">Lingi7</h1>
          <p className="mt-1 text-sm text-gray-500">Secure Commerce · Zambia</p>
        </div>

        <div className="card p-6">
          <h2 className="mb-5 text-lg font-semibold text-gray-900">Sign In</h2>

          {error && (
            <div className="mb-4 rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="space-y-4" onKeyDown={handleKey}>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Mobile Number
              </label>
              <PhoneInput
                value={phone}
                onChange={setPhone}
                error={fieldErrors.phone}
                hint="Enter 9 digits after +260 (e.g. 97, 77, 96, 76, 56, 57)"
              />
            </div>
            <FormField
              label="Password"
              type="password"
              value={password}
              onChange={setPassword}
              placeholder="Your password"
              autoComplete="current-password"
              error={fieldErrors.password}
            />
          </div>

          <button
            onClick={handleSubmit}
            disabled={isLoading}
            className="btn-primary mt-5 w-full py-3"
          >
            {isLoading ? "Signing in..." : "Sign In"}
          </button>

          <p className="mt-4 text-center text-sm text-gray-500">
            No account?{" "}
            <Link
              to="/register"
              className="font-medium text-emerald-600 hover:underline"
            >
              Create one
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
};

// ─── RegisterPage ─────────────────────────────────────────────────────────────

export const RegisterPage: React.FC = () => {
  const navigate = useNavigate();

  const [form, setForm] = useState<RegisterPayload>({
    phone_number: "",
    full_name: "",
    email: "",
    password: "",
    password_confirm: "",
    role: "BUYER",
    consent_given: false,
  });
  const [consent, setConsent] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const set =
    (key: keyof RegisterPayload) =>
    (value: string) =>
      setForm((prev) => ({ ...prev, [key]: value }));

  const validate = (): Record<string, string> => {
    const errs: Record<string, string> = {};
    if (!isValidZambianPhone(form.phone_number)) {
      errs.phone_number = "Enter a valid MTN, Airtel, or Zamtel mobile number.";
    }
    if (!form.full_name.trim()) errs.full_name = "Full name is required.";
    if (form.password.length < 8)
      errs.password = "Password must be at least 8 characters.";
    if (form.password !== form.password_confirm)
      errs.password_confirm = "Passwords do not match.";
    if (!consent) errs.consent = "You must accept the Terms and Privacy Policy.";
    return errs;
  };

  const handleSubmit = async () => {
    setError(null);
    const errs = validate();
    if (Object.keys(errs).length) { setFieldErrors(errs); return; }

    setIsLoading(true);
    try {
      await authApi.register({ ...form, consent_given: consent });
      setSuccess(true);
    } catch (err) {
      setFieldErrors(extractFieldErrors(err));
      setError(extractMessage(err));
    } finally {
      setIsLoading(false);
    }
  };

  if (success) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
        <div className="w-full max-w-sm card p-8 text-center">
          <div className="text-5xl mb-4">✅</div>
          <h2 className="text-xl font-bold text-gray-900">Account Created!</h2>
          <p className="mt-2 text-sm text-gray-500">
            Your account is ready. Sign in to start shopping securely.
          </p>
          <button
            onClick={() => navigate("/login")}
            className="btn-primary mt-6 w-full py-3"
          >
            Sign In
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-10">
      <div className="w-full max-w-sm">
        {/* Brand */}
        <div className="mb-8 text-center">
          <h1 className="text-4xl font-black text-emerald-600">Lingi7</h1>
          <p className="mt-1 text-sm text-gray-500">Create your account</p>
        </div>

        <div className="card p-6">
          {error && (
            <div className="mb-4 rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="space-y-4">
            {/* Account type toggle */}
            <div>
              <p className="mb-2 text-sm font-medium text-gray-700">I am a</p>
              <div className="grid grid-cols-2 gap-2">
                {(["BUYER", "VENDOR"] as const).map((role) => (
                  <button
                    key={role}
                    onClick={() => set("role")(role)}
                    className={`rounded-lg border-2 py-2.5 text-sm font-medium transition-colors min-h-0 ${
                      form.role === role
                        ? "border-emerald-500 bg-emerald-50 text-emerald-700"
                        : "border-gray-200 text-gray-600 hover:border-gray-300"
                    }`}
                  >
                    {role === "BUYER" ? "Buyer" : "Vendor / Seller"}
                  </button>
                ))}
              </div>
            </div>

            <FormField
              label="Full Name"
              value={form.full_name}
              onChange={set("full_name")}
              placeholder="Your full legal name"
              autoComplete="name"
              error={fieldErrors.full_name}
            />
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Mobile Number
              </label>
              <PhoneInput
                value={form.phone_number}
                onChange={set("phone_number")}
                error={fieldErrors.phone_number}
              />
            </div>
            <FormField
              label="Email (optional)"
              type="email"
              value={form.email ?? ""}
              onChange={set("email")}
              placeholder="you@example.com"
              autoComplete="email"
              error={fieldErrors.email}
            />
            <FormField
              label="Password"
              type="password"
              value={form.password}
              onChange={set("password")}
              placeholder="Minimum 8 characters"
              autoComplete="new-password"
              error={fieldErrors.password}
            />
            <FormField
              label="Confirm Password"
              type="password"
              value={form.password_confirm}
              onChange={set("password_confirm")}
              placeholder="Re-enter password"
              autoComplete="new-password"
              error={fieldErrors.password_confirm}
            />
          </div>

          <label className="mt-4 flex items-start gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-gray-300 text-emerald-600"
            />
            <span>
              I agree to the Terms of Service and Privacy Policy. My data is processed
              under the Zambia Data Protection Act 2021.
            </span>
          </label>
          {fieldErrors.consent && (
            <p className="text-xs text-red-600">{fieldErrors.consent}</p>
          )}

          <button
            onClick={handleSubmit}
            disabled={isLoading}
            className="btn-primary mt-4 w-full py-3"
          >
            {isLoading ? "Creating account..." : "Create Account"}
          </button>

          <p className="mt-4 text-center text-sm text-gray-500">
            Already have an account?{" "}
            <Link
              to="/login"
              className="font-medium text-emerald-600 hover:underline"
            >
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
};
