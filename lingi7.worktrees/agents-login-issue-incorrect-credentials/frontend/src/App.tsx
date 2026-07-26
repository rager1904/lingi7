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

import React, { Suspense, lazy } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  Outlet,
  useLocation,
} from "react-router-dom";
import { useAuthStore, useCartStore } from "./store";
import TopBar from "./components/layout/TopBar";
import BottomNav from "./components/layout/BottomNav";

// ─── Lazy pages ───────────────────────────────────────────────────────────────
const HomePage           = lazy(() => import("./pages/HomePage"));
const ProductDetailPage  = lazy(() => import("./pages/ProductDetailPage"));
const CheckoutPage       = lazy(() => import("./pages/CheckoutPage"));
const OrderHistoryPage   = lazy(() => import("./pages/OrderHistoryPage"));
const OrderDetailPage    = lazy(() => import("./pages/OrderDetailPage"));
const AccountPage        = lazy(() => import("./pages/AccountPage"));
const KYCUploadPage      = lazy(() => import("./pages/KYCUploadPage"));
const PublicTrackingPage = lazy(() => import("./pages/PublicTrackingPage"));
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
  <div className="flex min-h-screen flex-col bg-gray-50">
    <TopBar />
    <main className="flex-1 pb-20">
      <Suspense fallback={<Spinner />}>
        <Outlet />
      </Suspense>
    </main>
    <BottomNav />
  </div>
);

// Fullscreen layout — no chrome (login, register, public tracking)
const BareLayout: React.FC = () => (
  <Suspense fallback={<Spinner fullPage />}>
    <Outlet />
  </Suspense>
);

// ─── App ──────────────────────────────────────────────────────────────────────
const App: React.FC = () => (
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
        <Route path="/products/:slug"  element={<ProductDetailPage />} />

        {/* Protected */}
        <Route element={<RequireAuth />}>
          <Route path="/checkout"          element={<CheckoutPage />} />
          <Route path="/orders"            element={<OrderHistoryPage />} />
          <Route path="/orders/:orderId"   element={<OrderDetailPage />} />
          <Route path="/account"           element={<AccountPage />} />
          <Route path="/account/kyc"       element={<KYCUploadPage />} />
        </Route>
      </Route>

      {/* Catch-all */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  </BrowserRouter>
);

export default App;
