/**
 * PhoneInput — Zambian mobile with fixed +260 country prefix
 */

import React, { useEffect, useState } from "react";
import {
  isValidZambianPhone,
  normalizeZambianPhone,
  splitZambianPhoneLocal,
} from "../../utils";

interface PhoneInputProps {
  value: string;
  onChange: (e164: string) => void;
  error?: string;
  hint?: string;
  disabled?: boolean;
  id?: string;
  placeholder?: string;
}

export const PhoneInput: React.FC<PhoneInputProps> = ({
  value,
  onChange,
  error,
  hint,
  disabled,
  id,
  placeholder = "971234567",
}) => {
  const [local, setLocal] = useState(() => splitZambianPhoneLocal(value));

  useEffect(() => {
    setLocal(splitZambianPhoneLocal(value));
  }, [value]);

  const handleLocalChange = (raw: string) => {
    const digits = raw.replace(/\D/g, "").slice(0, 9);
    setLocal(digits);
    onChange(digits ? `+260${digits}` : "+260");
  };

  const full = normalizeZambianPhone(value || `+260${local}`);
  const showInvalid = local.length === 9 && !isValidZambianPhone(full);

  return (
    <div>
      <div
        className={`flex overflow-hidden rounded-lg border bg-white focus-within:ring-2 focus-within:ring-emerald-500 ${
          error || showInvalid ? "border-red-400" : "border-gray-300"
        }`}
      >
        <span
          className="flex items-center border-r border-gray-200 bg-gray-50 px-3 text-sm font-medium text-gray-600 select-none"
          aria-hidden
        >
          +260
        </span>
        <input
          id={id}
          type="tel"
          inputMode="numeric"
          autoComplete="tel-national"
          disabled={disabled}
          value={local}
          onChange={(e) => handleLocalChange(e.target.value)}
          placeholder={placeholder}
          className="min-w-0 flex-1 border-0 px-3 py-2 text-sm focus:outline-none focus:ring-0"
          aria-label="Mobile number without country code"
        />
      </div>
      {hint && !error && !showInvalid && (
        <p className="mt-1 text-xs text-gray-500">{hint}</p>
      )}
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
      {!error && showInvalid && (
        <p className="mt-1 text-xs text-red-600">
          Use MTN (96/76/56), Airtel (97/77/57), or Zamtel (95/75/55).
        </p>
      )}
    </div>
  );
};

export default PhoneInput;
