/**
 * FormField — labeled input wrapper for vendor/admin forms
 */

import React from "react";

interface FormFieldProps {
  label: string;
  required?: boolean;
  error?: string;
  hint?: string;
  children: React.ReactNode;
}

export const FormField: React.FC<FormFieldProps> = ({
  label,
  required,
  error,
  hint,
  children,
}) => (
  <div>
    <label className="mb-1 block text-sm font-medium text-gray-700">
      {label}
      {required && <span className="text-red-500"> *</span>}
    </label>
    {children}
    {hint && !error && <p className="mt-1 text-xs text-gray-500">{hint}</p>}
    {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
  </div>
);

export default FormField;
