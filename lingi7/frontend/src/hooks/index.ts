/**
 * Lingi7 Custom Hooks
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { authApi } from "../api/auth";
import { ordersApi, paymentsApi, logisticsApi, recommendationsApi } from "../api";
import { useAuthStore, useWishlistStore } from "../store";
import type {
  Order,
  OrderListItem,
  PaginatedResponse,
  PaymentAttempt,
  ProductListItem,
  RecommendationSection,
  Shipment,
  User,
  WishlistItem,
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
      const pageResults = resp.results ?? [];
      setOrders((prev) => (reset || p === 1 ? pageResults : [...prev, ...pageResults]));
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

export function useOrder(orderId: string | null): {
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
export function usePaymentPoller(
  paymentId: string | null,
  options?: { onTerminalFailure?: (message: string) => void }
): {
  attempt: PaymentAttempt | null;
  isPolling: boolean;
  stopPolling: () => void;
} {
  const [attempt, setAttempt] = useState<PaymentAttempt | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const onFailure = options?.onTerminalFailure;

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
        if (
          result.status === "SUCCESS" ||
          result.status === "FAILED" ||
          result.status === "CANCELLED"
        ) {
          stop();
        }
      } catch (err) {
        stop();
        onFailure?.(extractMessage(err));
      }
    };

    poll();
    intervalRef.current = setInterval(poll, 5_000);

    return stop;
  }, [paymentId, stop, onFailure]);

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
    logisticsApi
      .trackByToken(token)
      .then(setShipment)
      .catch((err) => setError(extractMessage(err)))
      .finally(() => setIsLoading(false));
  }, [token]);

  return { shipment, isLoading, error };
}

// ─── useOrderTracking ─────────────────────────────────────────────────────────

/** Order shipments are embedded on OrderSerializer.shipment (orders app). */
export function useOrderTracking(_orderId: string | null): {
  shipment: Shipment | null;
  isLoading: boolean;
  error: string | null;
} {
  void _orderId;
  return { shipment: null, isLoading: false, error: null };
}

// ─── useDisputes ──────────────────────────────────────────────────────────────

export function useDisputes(): {
  disputes: import("../types").Dispute[];
  isLoading: boolean;
  error: string | null;
  refresh: () => void;
} {
  const [disputes, setDisputes] = useState<import("../types").Dispute[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setIsLoading(true);
    ordersApi
      .listDisputes()
      .then((rows) => setDisputes(rows))
      .catch((err) => setError(extractMessage(err)))
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { disputes, isLoading, error, refresh };
}

// ─── useForYou ──────────────────────────────────────────────────────────────

export function useForYou(limit = 20) {
  const { isAuthenticated } = useAuthStore();
  return useQuery<RecommendationSection[]>({
    queryKey: ["for-you", limit],
    queryFn: async () => {
      const resp = await recommendationsApi.getForYou(limit);
      return resp.data;
    },
    enabled: isAuthenticated,
    staleTime: 1000 * 60 * 15, // 15 minutes
  });
}

// ─── useTrending ────────────────────────────────────────────────────────────

export function useTrending(limit = 20) {
  return useQuery<ProductListItem[]>({
    queryKey: ["trending", limit],
    queryFn: async () => {
      const resp = await recommendationsApi.getTrending(limit);
      return resp.data;
    },
    staleTime: 1000 * 60 * 10, // 10 minutes
  });
}

// ─── useSimilarProducts ─────────────────────────────────────────────────────

export function useSimilarProducts(productId: number | null, limit = 10) {
  return useQuery<ProductListItem[]>({
    queryKey: ["similar-products", productId, limit],
    queryFn: async () => {
      const resp = await recommendationsApi.getSimilar(productId!, limit);
      return resp.data;
    },
    enabled: !!productId,
    staleTime: 1000 * 60 * 15,
  });
}

// ─── useLikeToggle ──────────────────────────────────────────────────────────

export function useLikeToggle() {
  const queryClient = useQueryClient();
  const { toggleLiked } = useWishlistStore();

  return useMutation({
    mutationFn: (productId: number) => recommendationsApi.toggleLike(productId),
    onMutate: (productId) => {
      // Optimistic update
      toggleLiked(productId);
    },
    onError: (_err, productId) => {
      // Revert on error
      toggleLiked(productId);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["likes"] });
      queryClient.invalidateQueries({ queryKey: ["for-you"] });
    },
  });
}

// ─── useWishlist ────────────────────────────────────────────────────────────

export function useWishlist() {
  const queryClient = useQueryClient();
  const { setWishlistProductIds, setTotalCount, addToWishlist, removeFromWishlist } = useWishlistStore();

  const query = useQuery<{ results: WishlistItem[]; count: number }>({
    queryKey: ["wishlist"],
    queryFn: async () => {
      const resp = await recommendationsApi.listWishlist();
      setWishlistProductIds(resp.results.map((item) => item.product));
      setTotalCount(resp.count);
      return resp;
    },
  });

  const addMutation = useMutation({
    mutationFn: ({ productId, name, note }: { productId: number; name?: string; note?: string }) =>
      recommendationsApi.addToWishlist(productId, name, note),
    onMutate: ({ productId }) => {
      addToWishlist(productId);
    },
    onError: (_err, { productId }) => {
      removeFromWishlist(productId);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["wishlist"] });
    },
  });

  const removeMutation = useMutation({
    mutationFn: (itemId: number) => recommendationsApi.removeFromWishlist(itemId),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["wishlist"] });
    },
  });

  return {
    ...query,
    addToWishlist: addMutation.mutate,
    removeFromWishlist: removeMutation.mutate,
    isAdding: addMutation.isPending,
    isRemoving: removeMutation.isPending,
  };
}

// ─── useTrackView ───────────────────────────────────────────────────────────

export function useTrackView() {
  return useMutation({
    mutationFn: (productId: number) => recommendationsApi.trackView(productId),
  });
}
