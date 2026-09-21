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

/** Downscale limit for uploaded identity photos. */
const MAX_UPLOAD_DIMENSION = 1600;
/** JPEG quality after compression. */
const JPEG_QUALITY = 0.8;

/**
 * Compress an identity photo so KYC uploads are small enough to finish within
 * the client timeout on slow mobile links. A phone camera image of several MB
 * becomes ~100-300KB. Images already under 250KB (or non-images) pass through.
 */
async function compressImage(file: File): Promise<Blob> {
  if (file.size <= 250 * 1024 || !file.type.startsWith("image/")) {
    return file;
  }
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(
    1,
    MAX_UPLOAD_DIMENSION / Math.max(bitmap.width, bitmap.height)
  );
  const width = Math.max(1, Math.round(bitmap.width * scale));
  const height = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) {
    bitmap.close();
    return file;
  }
  context.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();
  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob(
      (blob) =>
        blob ? resolve(blob) : reject(new Error("Image compression failed.")),
      "image/jpeg",
      JPEG_QUALITY
    );
  });
}

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
   * Photos are compressed client-side and the call is given a long timeout so
   * uploads survive slow mobile links.
   */
  submitKYC: async (formData: FormData): Promise<{ detail: string }> => {
    const [front, back, selfie] = await Promise.all([
      compressImage(formData.get("nrc_front") as File),
      compressImage(formData.get("nrc_back") as File),
      compressImage(formData.get("selfie") as File),
    ]);

    const payload = new FormData();
    for (const key of ["nrc_number", "physical_address", "province"]) {
      const value = formData.get(key);
      if (value !== null) payload.append(key, String(value));
    }
    payload.append("nrc_front", front, "nrc_front.jpg");
    payload.append("nrc_back", back, "nrc_back.jpg");
    payload.append("selfie", selfie, "selfie.jpg");

    const { data } = await apiClient.post<{ detail: string }>(
      "/auth/kyc/upload/",
      payload,
      { timeout: 120_000 }
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
