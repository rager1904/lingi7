/**
 * Lingi7 API Client — Base Axios instance
 *
 * Handles:
 *   - JWT access token injection
 *   - Silent access token refresh on 401
 *   - Redirect to login on refresh failure
 *   - Consistent error shape normalisation
 */

import axios, {
  AxiosError,
  AxiosInstance,
  AxiosResponse,
  InternalAxiosRequestConfig,
} from "axios";
import type { APIError, AuthTokens } from "../types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// Token storage helpers — sessionStorage for access, localStorage for refresh
const TokenStorage = {
  getAccess: (): string | null => sessionStorage.getItem("access_token"),
  setAccess: (token: string): void => sessionStorage.setItem("access_token", token),
  getRefresh: (): string | null => localStorage.getItem("refresh_token"),
  setRefresh: (token: string): void => localStorage.setItem("refresh_token", token),
  setTokens: (tokens: AuthTokens): void => {
    TokenStorage.setAccess(tokens.access);
    TokenStorage.setRefresh(tokens.refresh);
  },
  clear: (): void => {
    sessionStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
  },
};

export { TokenStorage };

// ─── Axios instance ───────────────────────────────────────────────────────────

const apiClient: AxiosInstance = axios.create({
  baseURL: `${BASE_URL}/api`,
  timeout: 30_000,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

// Request interceptor — inject access token
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = TokenStorage.getAccess();
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Track in-flight refresh to avoid concurrent refresh storms
let isRefreshing = false;
let refreshQueue: Array<{
  resolve: (token: string) => void;
  reject: (err: unknown) => void;
}> = [];

function processQueue(error: unknown, token: string | null = null): void {
  refreshQueue.forEach(({ resolve, reject }) => {
    if (error) {
      reject(error);
    } else if (token) {
      resolve(token);
    }
  });
  refreshQueue = [];
}

// Response interceptor — refresh on 401
apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    if (error.response?.status !== 401 || originalRequest._retry) {
      return Promise.reject(normaliseError(error));
    }

    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        refreshQueue.push({ resolve, reject });
      }).then((token) => {
        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${token}`;
        }
        return apiClient(originalRequest);
      });
    }

    originalRequest._retry = true;
    isRefreshing = true;

    const refreshToken = TokenStorage.getRefresh();
    if (!refreshToken) {
      TokenStorage.clear();
      window.location.href = "/login";
      return Promise.reject(normaliseError(error));
    }

    try {
      const { data } = await axios.post<AuthTokens>(
        `${BASE_URL}/api/auth/token/refresh/`,
        { refresh: refreshToken }
      );
      TokenStorage.setTokens(data);
      processQueue(null, data.access);
      if (originalRequest.headers) {
        originalRequest.headers.Authorization = `Bearer ${data.access}`;
      }
      return apiClient(originalRequest);
    } catch (refreshError) {
      processQueue(refreshError, null);
      TokenStorage.clear();
      window.location.href = "/login";
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);

// ─── Error normalisation ─────────────────────────────────────────────────────

export function normaliseError(error: AxiosError): { message: string; fields: APIError } {
  const data = error.response?.data as APIError | undefined;

  if (!data) {
    return {
      message: error.message || "Network error. Please check your connection.",
      fields: {},
    };
  }

  const message =
    typeof data.detail === "string"
      ? data.detail
      : "An error occurred. Please try again.";

  return { message, fields: data };
}

export default apiClient;
