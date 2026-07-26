/**
 * Lingi7 Global State — Zustand stores
 *
 * authStore  — user identity, persisted to sessionStorage
 * cartStore  — in-memory shopping cart (no persistence)
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { User } from "../types";

// ─── Auth Store ───────────────────────────────────────────────────────────────

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  setUser: (user: User | null) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      setUser: (user) => set({ user, isAuthenticated: !!user }),
      clearAuth: () => set({ user: null, isAuthenticated: false }),
    }),
    {
      name: "lingi7_auth",
      storage: createJSONStorage(() => sessionStorage),
      // Only persist identity — not sensitive tokens (those are in TokenStorage)
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
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
}

interface CartState {
  items: CartItem[];
  addItem: (item: Omit<CartItem, "quantity">) => void;
  removeItem: (productId: number) => void;
  updateQuantity: (productId: number, quantity: number) => void;
  clearCart: () => void;
  totalItems: () => number;
  totalZMW: () => string;
}

export const useCartStore = create<CartState>()((set, get) => ({
  items: [],

  addItem: (item) =>
    set((state) => {
      const existing = state.items.find((i) => i.product_id === item.product_id);
      if (existing) {
        return {
          items: state.items.map((i) =>
            i.product_id === item.product_id
              ? { ...i, quantity: Math.min(i.quantity + 1, i.max_stock) }
              : i
          ),
        };
      }
      return { items: [...state.items, { ...item, quantity: 1 }] };
    }),

  removeItem: (productId) =>
    set((state) => ({
      items: state.items.filter((i) => i.product_id !== productId),
    })),

  updateQuantity: (productId, quantity) =>
    set((state) => ({
      items: state.items
        .map((i) =>
          i.product_id === productId
            ? {
                ...i,
                quantity: Math.min(Math.max(1, quantity), i.max_stock),
              }
            : i
        )
        .filter((i) => i.quantity > 0),
    })),

  clearCart: () => set({ items: [] }),

  totalItems: () =>
    get().items.reduce((sum, item) => sum + item.quantity, 0),

  totalZMW: () => {
    const total = get().items.reduce(
      (sum, item) => sum + parseFloat(item.price_zmw) * item.quantity,
      0
    );
    return total.toFixed(2);
  },
}));
