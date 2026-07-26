/**
 * Auth API — registration, login, logout, token refresh, KYC upload
 */

import apiClient, { TokenStorage } from "./client";
import type {
  AuthTokens,
  LoginPayload,
  RegisterPayload,
  User,
} from "../types";

export const authApi = {
  /**
   * Authenticate with phone number + password.
   * Stores tokens in browser storage on success.
   */
  login: async (payload: LoginPayload): Promise<User> => {
    const { data: tokens } = await apiClient.post<AuthTokens>(
      "/auth/token/",
      payload
    );
    TokenStorage.setTokens(tokens);
    const { data: user } = await apiClient.get<User>("/auth/me/");
    return user;
  },

  /**
   * Register a new BUYER or VENDOR account.
   */
  register: async (payload: RegisterPayload): Promise<{ detail: string }> => {
    const { data } = await apiClient.post<{ detail: string }>(
      "/auth/register/",
      payload
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
    const { data } = await apiClient.get<User>("/auth/me/");
    return data;
  },

  /**
   * Submit KYC documents (NRC photo, selfie).
   */
  submitKYC: async (formData: FormData): Promise<{ detail: string }> => {
    const { data } = await apiClient.post<{ detail: string }>(
      "/auth/kyc/upload/",
      formData,
      { headers: { "Content-Type": "multipart/form-data" } }
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
