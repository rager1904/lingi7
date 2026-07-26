/**
 * Auth API — registration, login, logout, token refresh, KYC upload
 */

import apiClient, { TokenStorage } from "./client";
import type {
  AuthTokens,
  LoginPayload,
  RegisterPayload,
  User,
  UserRole,
  KYCStatus,
} from "../types";
import { normalizeZambianPhone } from "../utils";

/** Map DRF profile / token payload into the frontend User shape. */
export function mapProfileToUser(data: Record<string, unknown>): User {
  const firstName = (data.first_name as string) || "";
  const lastName = (data.last_name as string) || "";
  const fullName =
    (data.full_name as string) || `${firstName} ${lastName}`.trim();

  return {
    id: String(data.id),
    phone_number: data.phone_number as string,
    full_name: fullName,
    email: (data.email as string) || null,
    role: data.role as UserRole,
    kyc_status: data.kyc_status as KYCStatus,
    is_active: data.is_active !== false && data.is_frozen !== true,
    is_frozen: data.is_frozen === true,
    date_joined: (data.date_joined as string) || new Date().toISOString(),
  };
}

interface TokenLoginResponse extends AuthTokens {
  user?: Record<string, unknown>;
}

export const authApi = {
  /**
   * Authenticate with phone number + password.
   * Stores tokens in browser storage on success.
   */
  login: async (payload: LoginPayload): Promise<User> => {
    const phone = normalizeZambianPhone(payload.phone_number);
    const { data: tokens } = await apiClient.post<TokenLoginResponse>(
      "/auth/token/",
      { ...payload, phone_number: phone }
    );
    TokenStorage.setTokens(tokens);

    try {
      const { data: profile } = await apiClient.get<Record<string, unknown>>(
        "/auth/me/"
      );
      return mapProfileToUser(profile);
    } catch {
      // Fallback if /me/ fails — still keep the session from JWT claims
      if (tokens.user) {
        return mapProfileToUser(tokens.user);
      }
      throw new Error("Signed in but could not load your profile. Please try again.");
    }
  },

  /**
   * Register a new BUYER or VENDOR account.
   */
  register: async (payload: RegisterPayload): Promise<{ detail: string }> => {
    const parts = payload.full_name.trim().split(/\s+/);
    const first_name = parts[0] ?? "";
    const last_name = parts.slice(1).join(" ") || first_name;

    const { data } = await apiClient.post<{ detail: string }>(
      "/auth/register/",
      {
        phone_number: normalizeZambianPhone(payload.phone_number),
        password: payload.password,
        password_confirm: payload.password_confirm,
        first_name,
        last_name,
        role: payload.role,
        email: payload.email?.trim() || "",
        consent_given: payload.consent_given,
      }
    );
    return data;
  },

  /**
   * Clear tokens and invalidate refresh on server.
   */
  logout: async (): Promise<void> => {
    const refresh = TokenStorage.getRefresh();
    if (refresh) {
      await apiClient.post("/auth/token/blacklist/", { refresh }).catch(() => {
        // Best-effort — clear locally regardless
      });
    }
    TokenStorage.clear();
  },

  /**
   * Fetch the currently authenticated user profile.
   */
  me: async (): Promise<User> => {
    const { data } = await apiClient.get<Record<string, unknown>>("/auth/me/");
    return mapProfileToUser(data);
  },

  /**
   * Submit KYC documents (NRC photo, selfie).
   */
  submitKYC: async (formData: FormData): Promise<{ detail: string }> => {
    // Let axios set multipart boundary automatically
    const { data } = await apiClient.post<{ detail: string }>(
      "/auth/kyc/upload/",
      formData
    );
    return data;
  },

  /**
   * Request a password reset OTP via SMS.
   */
  requestPasswordReset: async (phone_number: string): Promise<{ detail: string }> => {
    const { data } = await apiClient.post<{ detail: string }>(
      "/auth/password/reset/",
      { phone_number }
    );
    return data;
  },

  /**
   * Confirm password reset with OTP and new password.
   */
  confirmPasswordReset: async (
    phone_number: string,
    otp: string,
    new_password: string
  ): Promise<{ detail: string }> => {
    const { data } = await apiClient.post<{ detail: string }>(
      "/auth/password/reset/confirm/",
      { phone_number, otp, new_password }
    );
    return data;
  },
};
