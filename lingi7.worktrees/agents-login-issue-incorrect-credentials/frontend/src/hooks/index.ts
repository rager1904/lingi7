/**
 * Lingi7 Custom Hooks
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { authApi } from "../api/auth";
import { ordersApi, paymentsApi, trackingApi } from "../api/resources";
import { useAuthStore } from "../store";
import type {
  Order,
  OrderListItem,
  PaginatedResponse,
  PaymentAttempt,
  Shipment,
  User,
} from "../types";
import { extractMessage } from "../utils";

// ─── useAuth ──────────────────────────────────────────────────────────────────

interface UseAuthReturn {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (phone: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  error: string | null;
}

export function useAuth(): UseAuthReturn {
  const { user, isAuthenticated, setUser, clearAuth } = useAuthStore();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const login = useCallback(
    async (phone_number: string, password: string) => {
      setIsLoading(true);
      setError(null);
      try {
        const loggedInUser = await authApi.login({ phone_number, password });
        setUser(loggedInUser);
      } catch (err) {
        const msg = extractMessage(err);
        setError(msg);
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    [setUser]
  );

  const logout = useCallback(async () => {
    await authApi.logout();
    clearAuth();
  }, [clearAuth]);

  return { user, isAuthenticated, isLoading, login, logout, error };
}

// ─── useCurrentUser ───────────────────────────────────────────────────────────

export function useCurrentUser(): { user: User | null; isLoading: boolean } {
  const { user, setUser } = useAuthStore();
  const [isLoading, setIsLoading] = useState(!user);

  useEffect(() => {
    if (user) { setIsLoading(false); return; }
    authApi
      .me()
      .then(setUser)
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return { user, isLoading };
}

// ─── useOrders ────────────────────────────────────────────────────────────────

interface UseOrdersReturn {
  orders: OrderListItem[];
  isLoading: boolean;
  error: string | null;
  hasMore: boolean;
  loadMore: () => void;
  refresh: () => void;
}

export function useOrders(): UseOrdersReturn {
  const [orders, setOrders] = useState<OrderListItem[]>([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPage = useCallback(async (p: number, reset = false) => {
    setIsLoading(true);
    setError(null);
    try {
      const resp: PaginatedResponse<OrderListItem> = await ordersApi.list(p);
      setOrders((prev) => (reset || p === 1 ? resp.results : [...prev, ...resp.results]));
      setHasMore(!!resp.next);
    } catch (err) {
      setError(extractMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPage(1);
  }, [fetchPage]);

  const loadMore = useCallback(() => {
    if (!isLoading && hasMore) {
      const next = page + 1;
      setPage(next);
      fetchPage(next);
    }
  }, [isLoading, hasMore, page, fetchPage]);

  const refresh = useCallback(() => {
    setPage(1);
    fetchPage(1, true);
  }, [fetchPage]);

  return { orders, isLoading, error, hasMore, loadMore, refresh };
}

// ─── useOrder ─────────────────────────────────────────────────────────────────

export function useOrder(orderId: number | null): {
  order: Order | null;
  isLoading: boolean;
  error: string | null;
  refresh: () => void;
} {
  const [order, setOrder] = useState<Order | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(() => {
    if (!orderId) return;
    setIsLoading(true);
    ordersApi
      .retrieve(orderId)
      .then(setOrder)
      .catch((err) => setError(extractMessage(err)))
      .finally(() => setIsLoading(false));
  }, [orderId]);

  useEffect(() => { fetch(); }, [fetch]);

  return { order, isLoading, error, refresh: fetch };
}

// ─── usePaymentPoller ─────────────────────────────────────────────────────────

/**
 * Polls payment status every 5 seconds while status is PENDING.
 * Automatically stops on SUCCESS or FAILED.
 */
export function usePaymentPoller(paymentId: number | null): {
  attempt: PaymentAttempt | null;
  isPolling: boolean;
  stopPolling: () => void;
} {
  const [attempt, setAttempt] = useState<PaymentAttempt | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setIsPolling(false);
  }, []);

  useEffect(() => {
    if (!paymentId) return;

    setIsPolling(true);

    const poll = async () => {
      try {
        const result = await paymentsApi.pollStatus(paymentId);
        setAttempt(result);
        if (result.status === "SUCCESS" || result.status === "FAILED") {
          stop();
        }
      } catch {
        stop();
      }
    };

    poll(); // immediate first call
    intervalRef.current = setInterval(poll, 5_000);

    return stop;
  }, [paymentId, stop]);

  return { attempt, isPolling, stopPolling: stop };
}

// ─── useTrackingByToken ───────────────────────────────────────────────────────

export function useTrackingByToken(token: string | null): {
  shipment: Shipment | null;
  isLoading: boolean;
  error: string | null;
} {
  const [shipment, setShipment] = useState<Shipment | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    setIsLoading(true);
    trackingApi
      .byToken(token)
      .then(setShipment)
      .catch((err) => setError(extractMessage(err)))
      .finally(() => setIsLoading(false));
  }, [token]);

  return { shipment, isLoading, error };
}

// ─── useOrderTracking ─────────────────────────────────────────────────────────

export function useOrderTracking(orderId: number | null): {
  shipment: Shipment | null;
  isLoading: boolean;
  error: string | null;
} {
  const [shipment, setShipment] = useState<Shipment | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!orderId) return;
    setIsLoading(true);
    trackingApi
      .byOrder(orderId)
      .then(setShipment)
      .catch((err) => setError(extractMessage(err)))
      .finally(() => setIsLoading(false));
  }, [orderId]);

  return { shipment, isLoading, error };
}
