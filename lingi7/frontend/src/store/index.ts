/**
 * Lingi7 Global State — Zustand stores
 *
 * authStore    — user identity, persisted to sessionStorage
 * cartStore    — shopping cart, persisted to localStorage
 * wishlistStore — saved products, synced with backend
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { User } from "../types";
import apiClient from "../api/client";

// ─── Auth Store ───────────────────────────────────────────────────────────────

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  /** False until sessionStorage rehydration finishes — prevents login state being wiped. */
  _hasHydrated: boolean;
  setUser: (user: User | null) => void;
  clearAuth: () => void;
  setHasHydrated: (value: boolean) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      _hasHydrated: false,
      setUser: (user) => set({ user, isAuthenticated: !!user }),
      clearAuth: () => set({ user: null, isAuthenticated: false }),
      setHasHydrated: (value) => set({ _hasHydrated: value }),
    }),
    {
      name: "lingi7_auth",
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
    }
  )
);

// ─── Cart Store ───────────────────────────────────────────────────────────────

export interface CartItem {
  product_id: number;
  product_name: string;
  price_zmw: string;
  quantity: number;
  image_url: string | null;
  max_stock: number;
  seller_id: string;
}

interface CartState {
  items: CartItem[];
  /** Shown once when cart is replaced due to different seller. */
  sellerSwitchNotice: string | null;
  addItem: (item: Omit<CartItem, "quantity">, quantity?: number) => void;
  removeItem: (productId: number) => void;
  updateQuantity: (productId: number, quantity: number) => void;
  clearCart: () => void;
  clearSellerSwitchNotice: () => void;
  totalItems: () => number;
  totalZMW: () => string;
}

export const useCartStore = create<CartState>()(
  persist(
    (set, get) => ({
      items: [],
      sellerSwitchNotice: null,

      addItem: (item, quantity = 1) => {
        set((state) => {
          if (
            state.items.length > 0 &&
            state.items[0].seller_id !== item.seller_id
          ) {
            return {
              items: [{ ...item, quantity: Math.min(quantity, item.max_stock) }],
              sellerSwitchNotice:
                "Your cart was cleared because items must be from one vendor at a time.",
            };
          }
          const existing = state.items.find((i) => i.product_id === item.product_id);
          if (existing) {
            return {
              items: state.items.map((i) =>
                i.product_id === item.product_id
                  ? { ...i, quantity: Math.min(i.quantity + quantity, i.max_stock) }
                  : i
              ),
              sellerSwitchNotice: null,
            };
          }
          return {
            items: [
              ...state.items,
              { ...item, quantity: Math.min(Math.max(1, quantity), item.max_stock) },
            ],
            sellerSwitchNotice: null,
          };
        });
        apiClient.post("/cart/add/", {
          item: item.product_name,
          amount: quantity,
          price: parseFloat(item.price_zmw),
        }).catch(() => {});
      },

      removeItem: (productId) => {
        const item = get().items.find((i) => i.product_id === productId);
        set((state) => ({
          items: state.items.filter((i) => i.product_id !== productId),
        }));
        if (item) {
          apiClient.post("/cart/remove/", {
            item: item.product_name,
            amount: item.quantity,
          }).catch(() => {});
        }
      },

      updateQuantity: (productId, quantity) => {
        const old = get().items.find((i) => i.product_id === productId);
        set((state) => ({
          items: state.items
            .map((i) =>
              i.product_id === productId
                ? { ...i, quantity: Math.min(Math.max(1, quantity), i.max_stock) }
                : i
            )
            .filter((i) => i.quantity > 0),
        }));
        if (old) {
          const newQty = Math.min(Math.max(1, quantity), old.max_stock);
          const delta = newQty - old.quantity;
          if (delta > 0) {
            apiClient.post("/cart/add/", {
              item: old.product_name,
              amount: delta,
              price: parseFloat(old.price_zmw),
            }).catch(() => {});
          } else if (delta < 0) {
            apiClient.post("/cart/remove/", {
              item: old.product_name,
              amount: Math.abs(delta),
            }).catch(() => {});
          }
        }
      },

      clearCart: () => set({ items: [], sellerSwitchNotice: null }),
      clearSellerSwitchNotice: () => set({ sellerSwitchNotice: null }),

      totalItems: () =>
        get().items.reduce((sum, item) => sum + item.quantity, 0),

      totalZMW: () => {
        const total = get().items.reduce(
          (sum, item) => sum + parseFloat(item.price_zmw) * item.quantity,
          0
        );
        return total.toFixed(2);
      },
    }),
    {
      name: "lingi7_cart",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ items: state.items }),
    }
  )
);

// ─── Wishlist Store ───────────────────────────────────────────────────────────

interface WishlistState {
  /** Set of product IDs the user has liked (for instant heart toggling). */
  likedProductIds: Set<number>;
  /** Local cache of wishlist product IDs. */
  wishlistProductIds: Set<number>;
  /** Total count from server. */
  totalCount: number;
  setLikedProductIds: (ids: number[]) => void;
  setWishlistProductIds: (ids: number[]) => void;
  toggleLiked: (productId: number) => void;
  addToWishlist: (productId: number) => void;
  removeFromWishlist: (productId: number) => void;
  setTotalCount: (count: number) => void;
  isLiked: (productId: number) => boolean;
  isWishlisted: (productId: number) => boolean;
}

export const useWishlistStore = create<WishlistState>()((set, get) => ({
  likedProductIds: new Set(),
  wishlistProductIds: new Set(),
  totalCount: 0,

  setLikedProductIds: (ids) => set({ likedProductIds: new Set(ids) }),
  setWishlistProductIds: (ids) => set({ wishlistProductIds: new Set(ids) }),
  setTotalCount: (count) => set({ totalCount: count }),

  toggleLiked: (productId) =>
    set((state) => {
      const next = new Set(state.likedProductIds);
      if (next.has(productId)) {
        next.delete(productId);
      } else {
        next.add(productId);
      }
      return { likedProductIds: next };
    }),

  addToWishlist: (productId) =>
    set((state) => {
      const next = new Set(state.wishlistProductIds);
      next.add(productId);
      return { wishlistProductIds: next, totalCount: state.totalCount + 1 };
    }),

  removeFromWishlist: (productId) =>
    set((state) => {
      const next = new Set(state.wishlistProductIds);
      next.delete(productId);
      return { wishlistProductIds: next, totalCount: Math.max(0, state.totalCount - 1) };
    }),

  isLiked: (productId) => get().likedProductIds.has(productId),
  isWishlisted: (productId) => get().wishlistProductIds.has(productId),
}));
