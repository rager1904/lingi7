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
  baseURL: `${BASE_URL}/api/v1`,
  timeout: 30_000,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

// Request interceptor — inject access token; allow multipart file uploads
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = TokenStorage.getAccess();
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    // FormData must not use application/json — browser sets multipart boundary
    if (config.data instanceof FormData && config.headers) {
      const headers = config.headers as Record<string, unknown> & {
        delete?: (name: string) => boolean;
      };
      if (typeof headers.delete === "function") {
        headers.delete("Content-Type");
      } else {
        delete headers["Content-Type"];
        delete headers["content-type"];
      }
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

    const requestUrl = originalRequest.url ?? "";
    const isAuthEndpoint =
      requestUrl.includes("/auth/token") || requestUrl.includes("/auth/me");

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
      if (!isAuthEndpoint && !window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
      return Promise.reject(normaliseError(error));
    }

    try {
      const { data } = await axios.post<AuthTokens>(
        `${BASE_URL}/api/v1/auth/token/refresh/`,
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
      if (!isAuthEndpoint && !window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
      return Promise.reject(normaliseError(refreshError as AxiosError));
    } finally {
      isRefreshing = false;
    }
  }
);

// ─── Error normalisation ─────────────────────────────────────────────────────

interface Lingi7ErrorBody {
  error?: {
    message?: string;
    detail?: unknown;
    code?: string;
  };
  detail?: string | unknown;
  message?: string;
}

export function normaliseError(error: AxiosError): { message: string; fields: APIError } {
  const data = error.response?.data as Lingi7ErrorBody | undefined;

  if (!data) {
    return {
      message: error.message || "Network error. Please check your connection.",
      fields: {},
    };
  }

  let message: string | undefined;

  if (typeof data.error?.message === "string") {
    message = data.error.message;
  } else if (typeof data.detail === "string") {
    message = data.detail;
  } else if (typeof data.message === "string") {
    message = data.message;
  }

  const fields =
    data.error?.detail && typeof data.error.detail === "object"
      ? (data.error.detail as APIError)
      : {};

  return {
    message: message || "An error occurred. Please try again.",
    fields,
  };
}

export default apiClient;
