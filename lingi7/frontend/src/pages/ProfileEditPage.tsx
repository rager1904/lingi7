/**
 * ProfileEditPage — PATCH /api/v1/auth/me/
 */

import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { usersApi } from "../api/users";
import { useAuthStore } from "../store";
import { FormField } from "../components/forms/FormField";
import { extractFieldErrors, extractMessage } from "../utils";

const ProfileEditPage: React.FC = () => {
  const navigate = useNavigate();
  const { user, setUser } = useAuthStore();

  const [firstName, setFirstName] = useState(user?.full_name.split(" ")[0] ?? "");
  const [lastName, setLastName] = useState(
    user?.full_name.split(" ").slice(1).join(" ") ?? ""
  );
  const [email, setEmail] = useState(user?.email ?? "");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!user) {
      navigate("/login", { replace: true });
    }
  }, [user, navigate]);

  if (!user) return null;

  const handleSave = async () => {
    const errs: Record<string, string> = {};
    if (!firstName.trim()) errs.first_name = "First name is required.";
    if (!lastName.trim()) errs.last_name = "Last name is required.";
    if (Object.keys(errs).length) {
      setFieldErrors(errs);
      return;
    }

    setError(null);
    setFieldErrors({});
    setSaving(true);
    try {
      const updated = await usersApi.updateProfile({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim(),
      });
      setUser(updated);
      navigate("/account");
    } catch (err) {
      setFieldErrors(extractFieldErrors(err));
      setError(extractMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 space-y-4 sm:px-6">
      <button onClick={() => navigate("/account")} className="text-sm text-gray-500 min-h-0">
        ← Back
      </button>
      <p className="text-sm font-bold tracking-[.16em] text-blue-600">PROFILE</p>
      <h1 className="text-4xl font-black tracking-tight text-slate-950">Edit profile.</h1>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="card p-4 space-y-4">
        <FormField label="First name" required error={fieldErrors.first_name}>
          <input className="input" value={firstName} onChange={(e) => setFirstName(e.target.value)} />
        </FormField>
        <FormField label="Last name" required error={fieldErrors.last_name}>
          <input className="input" value={lastName} onChange={(e) => setLastName(e.target.value)} />
        </FormField>
        <FormField
          label="Email"
          hint="Optional. Used for receipts and account recovery."
          error={fieldErrors.email}
        >
          <input
            type="email"
            className="input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </FormField>
        <p className="text-xs text-gray-500">
          Phone {user?.phone_number} cannot be changed here. Contact support if needed.
        </p>
      </div>

      <button onClick={handleSave} disabled={saving} className="btn-primary w-full py-3">
        {saving ? "Saving..." : "Save Changes"}
      </button>
    </div>
  );
};

export default ProfileEditPage;
