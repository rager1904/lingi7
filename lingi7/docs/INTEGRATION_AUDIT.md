# Lingi7 Frontend–Backend Integration Audit

**Date:** 2026-05-30  
**Scope:** React SPA (`frontend/`) ↔ Django/DRF API (`/api/v1/`)  
**Status:** Critical integration gaps addressed in this session; full eCommerce parity still in progress.

---

## Production Readiness Scores

| Area | Score | Notes |
|------|-------|-------|
| **Frontend** | **68 / 100** | Core buyer + vendor flows exist; missing wishlist, reviews, coupons, admin UI |
| **Backend** | **78 / 100** | Strong domain services; notifications API empty; dual dispute systems |
| **Integration** | **72 / 100** | Up from ~55 after mapper fixes, vendor fulfilment UI, cart persistence |
| **Security** | **75 / 100** | P0 fixes applied (see `SECURITY_AUDIT.md`); JWT in localStorage remains |
| **UX** | **70 / 100** | Mobile-first shell; checkout improved; no dedicated cart route |
| **Performance** | **74 / 100** | Lazy routes; no React Query; list endpoints unpaginated on frontend |

---

## Feature Matrix

| Feature | Frontend | Backend | Working | Gap |
|---------|----------|---------|---------|-----|
| Auth (login/register/logout) | ✅ | ✅ | ✅ | Password reset API calls non-existent endpoints |
| KYC upload | ✅ | ✅ | ✅ | Key-based `/me/kyc/` unused |
| Product catalogue | ✅ | ✅ | ✅ | No sort/price filters in UI |
| Product detail + cart | ✅ | ✅ | ✅ | No reviews/related products |
| Server-side pricing checkout | ✅ | ✅ | ✅ | Fixed |
| MoMo payment + poll | ✅ | ✅ | ✅ | KYC gate UX added |
| Order history/detail | ✅ | ✅ | ✅ | — |
| Buyer cancel / confirm delivery | ✅ | ✅ | ✅ | — |
| Order disputes (orders app) | ✅ | ✅ | ✅ | Disputes app API unused |
| Public tracking | ✅ | ✅ | ✅ | Order detail lacks timeline |
| Vendor store register | ✅ | ✅ | ✅ | Store update PATCH not wired |
| Vendor products + AI enrich | ✅ | ✅ | ✅ | Archive/delete image not in UI |
| Vendor dashboard KPIs | ✅ | ✅ | ⚠️ | Real order counts wired (was stub) |
| Vendor order fulfilment | ✅ **new** | ✅ | ✅ | `/vendor/orders` page added |
| Wishlist | ❌ | ❌ | — | Not built |
| Coupons | ❌ | ❌ | — | Not built |
| Reviews/ratings | ❌ | ❌ | — | Not built |
| Notifications inbox | ❌ | ⚠️ models only | — | No REST API |
| Admin web UI | ❌ | ✅ Django admin + APIs | — | No React admin |
| Escrow admin | ❌ | ✅ read API | — | Staff-only |
| Fraud console | ❌ | ✅ internal API | — | — |

---

## Fixes Applied (This Session)

### Backend
- `PublicProductListSerializer` / `PublicProductDetailSerializer`: expose `stock_quantity` from inventory.
- `VendorDashboardView`: real `orders_pending_shipment` and `escrow_held_zmw` from orders.
- `OrderListCreateView`: `?role=seller|buyer` filter; GET no longer requires `CanTransact` (list history while unverified).

### Frontend
- **Mappers:** real stock counts; order line `product_id`; `delivery_fee_zmw` = 0 (platform fee separate).
- **Auth:** map `is_frozen` from profile; refresh profile on app load.
- **Cart:** persist to `localStorage`; seller-switch notice; checkout qty edit + remove.
- **Checkout:** KYC/frozen blocking UX; seller switch banner.
- **Account:** frozen account banner; loading state.
- **Vendor:** `/vendor/orders` fulfilment page (acknowledge + ship); dashboard link.
- **Vendor store:** normalize contact phone on registration.

---

## Critical Issues (Remaining)

| # | Issue | Severity | Location |
|---|-------|----------|----------|
| 1 | JWT refresh in `localStorage` (XSS risk) | High | `frontend/src/api/client.ts` |
| 2 | Password reset endpoints don't exist on backend | Medium | `frontend/src/api/auth.ts` |
| 3 | Dual dispute systems (orders vs disputes app) | Medium | Backend architecture |
| 4 | `disputesApi` unused; disputes list only page 1 of orders | Medium | `DisputesPage.tsx` |
| 5 | No notifications REST API | Medium | `apps/notifications/urls.py` |
| 6 | Vendor product PATCH/archive not in UI | Medium | `VendorProductsPage.tsx` |
| 7 | Order list API returns unpaginated array (frontend expects pagination) | Low | `orders/views.py` |

---

## Missing Features (eCommerce Parity)

**Buyer:** wishlist, saved addresses, product reviews, coupons, order search, newsletter, recommendations, dedicated `/cart` route.

**Vendor:** inventory bulk edit, payout history, analytics charts, store profile edit, logistics shipment API integration.

**Platform:** React admin for KYC/store/product review, notification centre, fraud review queue UI.

---

## Recommended Competitor-Grade Additions

1. One-tap MoMo re-pay from order detail when `PENDING_PAYMENT`.
2. SMS/email order status notifications (backend service exists; wire + UI prefs).
3. Trust badges on checkout (BoZ escrow, verified seller).
4. Product Q&A and seller response on listing pages.
5. Auto-confirm delivery countdown on order detail.

---

## Final Action Plan

### Priority 1 — Critical (before launch)
- [ ] HttpOnly cookie refresh tokens or BFF auth layer
- [ ] Paginate order list API + frontend
- [ ] Unify dispute model or document single path
- [ ] Remove or implement password reset endpoints

### Priority 2 — High
- [ ] Vendor store update UI (`PATCH /vendor/store/update/`)
- [ ] Order detail tracking timeline from `shipment` + public token link
- [ ] Notifications REST API + account inbox
- [ ] Product archive + image delete in vendor UI

### Priority 3 — Medium
- [ ] Price/sort filters on home catalogue
- [ ] Dedicated cart page (`/cart` → checkout)
- [ ] React Query for catalogue/orders cache
- [ ] Admin review SPA or improve Django admin 2FA

### Priority 4 — Low
- [ ] Wishlist model + UI
- [ ] Reviews/ratings
- [ ] Coupons/promotions
- [ ] Newsletter signup

---

## API Flow Reference (Happy Path Checkout)

```
HomePage → productsApi.list → GET /products/products/
ProductDetailPage → addItem(cart) → localStorage cart
CheckoutPage → ordersApi.create → POST /orders/ { seller_id, lines[{product_id, qty}] }
            → ordersApi.submit → POST /orders/{id}/submit/
            → paymentsApi.initiate → POST /payments/initiate/
            → poll GET /payments/{id}/status/
            → webhook → OrderService.confirm_payment → PAYMENT_RECEIVED
VendorOrdersPage → acknowledge → POST /orders/{id}/acknowledge/
                 → ship → POST /orders/{id}/ship/
OrderDetailPage → confirmDelivery → POST /orders/{id}/confirm-delivery/
```

---

## Test Checklist

- [ ] Add product to cart → refresh browser → cart persists
- [ ] Checkout with unverified KYC → blocked with message
- [ ] Vendor acknowledges + ships order from `/vendor/orders`
- [ ] Stock quantity on product page matches backend inventory
- [ ] `GET /orders/?role=seller` returns only seller orders
