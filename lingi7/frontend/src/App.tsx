/**
 * App.tsx — root router with auth guards, layout shell, lazy page loading
 *
 * Route map:
 *   /                    → HomePage (product catalogue)
 *   /products/:slug      → ProductDetailPage
 *   /checkout            → CheckoutPage           [auth required]
 *   /orders              → OrderHistoryPage        [auth required]
 *   /orders/:orderId     → OrderDetailPage         [auth required]
 *   /account             → AccountPage             [auth required]
 *   /account/kyc         → KYCUploadPage           [auth required]
 *   /login               → LoginPage
 *   /register            → RegisterPage
 *   /track/:token        → PublicTrackingPage      [public]
 */

import React, { Suspense, lazy, useEffect } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  Outlet,
  useLocation,
} from "react-router-dom";
import { useAuthStore } from "./store";
import TopBar from "./components/layout/TopBar";
import BottomNav from "./components/layout/BottomNav";
import Footer from "./components/layout/Footer";
import ShoppingAssistant from "./components/assistant/ShoppingAssistant";

// ─── Lazy pages ───────────────────────────────────────────────────────────────
const HomePage           = lazy(() => import("./pages/HomePage"));
const ProductListingPage = lazy(() => import("./pages/ProductListingPage"));
const ShopDirectoryPage  = lazy(() => import("./pages/ShopDirectoryPage"));
const StorefrontPage     = lazy(() => import("./pages/StorefrontPage"));
const CartPage           = lazy(() => import("./pages/CartPage"));
const WishlistPage       = lazy(() => import("./pages/WishlistPage"));
const NotificationsPage  = lazy(() => import("./pages/NotificationsPage"));
const PlatformDashboardPage = lazy(() => import("./pages/PlatformDashboardPage"));
const AdminManagementPage = lazy(() => import("./pages/AdminManagementPage"));
const ProductDetailPage  = lazy(() => import("./pages/ProductDetailPage"));
const CheckoutPage       = lazy(() => import("./pages/CheckoutPage"));
const OrderHistoryPage   = lazy(() => import("./pages/OrderHistoryPage"));
const OrderDetailPage    = lazy(() => import("./pages/OrderDetailPage"));
const AccountPage        = lazy(() => import("./pages/AccountPage"));
const KYCUploadPage        = lazy(() => import("./pages/KYCUploadPage"));
const ProfileEditPage      = lazy(() => import("./pages/ProfileEditPage"));
const DisputesPage         = lazy(() => import("./pages/DisputesPage"));
const VendorDashboardPage  = lazy(() => import("./pages/VendorDashboardPage"));
const VendorStorePage      = lazy(() => import("./pages/VendorStorePage"));
const VendorProductsPage   = lazy(() => import("./pages/VendorProductsPage"));
const VendorOrdersPage     = lazy(() => import("./pages/VendorOrdersPage"));
const VendorOperationsPage = lazy(() => import("./pages/VendorOperationsPage"));
const PublicTrackingPage   = lazy(() => import("./pages/PublicTrackingPage"));
const LoginPage          = lazy(() =>
  import("./pages/AuthPages").then((m) => ({ default: m.LoginPage }))
);
const RegisterPage = lazy(() =>
  import("./pages/AuthPages").then((m) => ({ default: m.RegisterPage }))
);

// ─── Loading fallback ─────────────────────────────────────────────────────────
const Spinner: React.FC<{ fullPage?: boolean }> = ({ fullPage }) => (
  <div
    className={`flex items-center justify-center ${
      fullPage ? "min-h-screen" : "min-h-64"
    }`}
  >
    <div className="h-8 w-8 animate-spin rounded-full border-4 border-emerald-200 border-t-emerald-600" />
  </div>
);

// ─── Auth guard ───────────────────────────────────────────────────────────────
const RequireAuth: React.FC = () => {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const location = useLocation();
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  return <Outlet />;
};

// Redirect logged-in users away from /login and /register
const GuestOnly: React.FC = () => {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return isAuthenticated ? <Navigate to="/" replace /> : <Outlet />;
};

// ─── Shared app layout (TopBar + BottomNav) ───────────────────────────────────
const AppLayout: React.FC = () => (
  <div className="mobile-nav-offset flex min-h-screen flex-col bg-gray-50">
    <TopBar />
    <main className="flex-1">
      <Suspense fallback={<Spinner />}>
        <Outlet />
      </Suspense>
    </main>
    <Footer />
    <ShoppingAssistant />
    <BottomNav />
  </div>
);

// Fullscreen layout — no chrome (login, register, public tracking)
const BareLayout: React.FC = () => (
  <Suspense fallback={<Spinner fullPage />}>
    <Outlet />
  </Suspense>
);

// Wait for persisted auth state before routing (avoids post-login redirect race).
const AuthHydrationGate: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const hasHydrated = useAuthStore((s) => s._hasHydrated);
  const setHasHydrated = useAuthStore((s) => s.setHasHydrated);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const setUser = useAuthStore((s) => s.setUser);

  useEffect(() => {
    if (useAuthStore.persist.hasHydrated()) {
      setHasHydrated(true);
      return;
    }
    return useAuthStore.persist.onFinishHydration(() => {
      setHasHydrated(true);
    });
  }, [setHasHydrated]);

  useEffect(() => {
    if (!hasHydrated || !isAuthenticated) return;
    import("./api/auth")
      .then(({ authApi }) => authApi.me())
      .then(setUser)
      .catch(() => {
        /* Token refresh / profile fetch handled by client interceptor */
      });
  }, [hasHydrated, isAuthenticated, setUser]);

  if (!hasHydrated) {
    return <Spinner fullPage />;
  }
  return <>{children}</>;
};

// ─── App ──────────────────────────────────────────────────────────────────────
const App: React.FC = () => (
  <AuthHydrationGate>
  <BrowserRouter>
    <Routes>
      {/* ── Bare (no nav chrome) ── */}
      <Route element={<BareLayout />}>
        {/* Public tracking — shareable link, no login */}
        <Route path="/track/:token" element={<PublicTrackingPage />} />

        {/* Guest-only auth pages */}
        <Route element={<GuestOnly />}>
          <Route path="/login"    element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Route>
      </Route>

      {/* ── App shell (TopBar + BottomNav) ── */}
      <Route element={<AppLayout />}>
        {/* Public browsing */}
        <Route path="/"                element={<HomePage />} />
        <Route path="/shop"             element={<ProductListingPage />} />
        <Route path="/shops"            element={<ShopDirectoryPage />} />
        <Route path="/shops/:slug"      element={<StorefrontPage />} />
        <Route path="/cart"             element={<CartPage />} />
        <Route path="/wishlist"         element={<WishlistPage />} />
        <Route path="/notifications"    element={<NotificationsPage />} />
        <Route path="/products/:slug"  element={<ProductDetailPage />} />

        {/* Protected */}
        <Route element={<RequireAuth />}>
          <Route path="/checkout"          element={<CheckoutPage />} />
          <Route path="/orders"            element={<OrderHistoryPage />} />
          <Route path="/orders/:orderId"   element={<OrderDetailPage />} />
          <Route path="/account"           element={<AccountPage />} />
          <Route path="/account/kyc"       element={<KYCUploadPage />} />
          <Route path="/account/profile"   element={<ProfileEditPage />} />
          <Route path="/dashboard"         element={<PlatformDashboardPage />} />
          <Route path="/admin/:section"    element={<AdminManagementPage />} />
          <Route path="/disputes"          element={<DisputesPage />} />
          <Route path="/vendor"            element={<VendorDashboardPage />} />
          <Route path="/vendor/store"      element={<VendorStorePage />} />
          <Route path="/vendor/products"   element={<VendorProductsPage />} />
          <Route path="/vendor/orders"     element={<VendorOrdersPage />} />
          <Route path="/vendor/:section"   element={<VendorOperationsPage />} />
        </Route>
      </Route>

      {/* Catch-all */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  </BrowserRouter>
  </AuthHydrationGate>
);

export default App;
