# Lingi7 Security & Production Readiness Audit

**Date:** 2026-05-30  
**Scope:** Full-stack eCommerce platform (Django/DRF backend, React frontend, payments, escrow, Docker)  
**Auditor perspective:** OWASP Top 10, fintech marketplace, bug bounty / active attacker model  

---

## Remediation Status (Important)

| Category | Applied? | Notes |
|----------|----------|-------|
| **P0 Critical (C1–C7)** | **Yes** | Server-side pricing, `CanTransact`, IDOR checks, webhook fail-closed, payment dedup + order confirm, KYC key validation, upload limits |
| **P1 High (H1–H3, H6)** | **Yes** | Approved listing edit block, auth throttle scope, `IsAdmin` standardization, escrow/order API alignment |
| **P1 High (H4–H5, H7)** | **Partial** | KYC upload size/type limits added; admin 2FA and HttpOnly refresh cookies **not** done |
| **Frontend page bugs (earlier session)** | **Yes** | Checkout fulfilment, order totals, disputes list, stock display, categories, vendor messaging, etc. |

---

# Executive Summary

| Metric | Score |
|--------|-------|
| **Overall Security Score** | **4.2 / 10** |
| **Production Readiness Score** | **5.0 / 10** |
| **Overall Risk Level** | **Critical** |

Lingi7 has a solid architectural foundation: JWT rotation/blacklisting, vendor queryset scoping, escrow state machines, Celery-based async work, and prod HTTPS/HSTS settings. However, several **Critical** flaws would be exploited immediately by bug bounty researchers or fraud rings:

- Client-controlled order pricing
- Webhook signature bypass paths
- Missing party authorization on order mutations
- KYC/compliance gates not wired to financial endpoints
- Payment/order/escrow integration gaps enabling double-charging and escrow manipulation

**Do not deploy to production serving real money until Critical findings C1–C7 are remediated and covered by integration tests.**

---

# Critical Findings

## C1. Client-controlled unit prices (price tampering)

**Severity:** Critical  
**OWASP:** A04 Insecure Design, A01 Broken Access Control  
**Files:** `apps/orders/serializers.py`, `apps/orders/services.py`

**Vulnerable code:**

```python
# apps/orders/serializers.py
class OrderLineCreateSerializer(serializers.Serializer):
    product_name = serializers.CharField(max_length=255)
    product_id   = serializers.CharField(max_length=100, required=False, default="")
    unit_price   = serializers.DecimalField(...)  # CLIENT-CONTROLLED
    quantity     = serializers.IntegerField(min_value=1, default=1)
```

```python
# apps/orders/services.py — total derived from client unit_price
price = Decimal(str(item["unit_price"]))
subtotal = sum(l.unit_price * l.quantity for l in line_objs)
order.total_amount = subtotal + fee
```

**Attack scenario:** Attacker sets `unit_price: 0.01` for a ZMW 5,000 product. MoMo charges the server-computed total, but that total is derived from tampered input. No lookup against `Product.price`, no seller ownership check.

**Fix:**

```python
# Accept only product_id + quantity
class OrderLineCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)

# Server-side price resolution
product = Product.objects.select_related("store").get(
    pk=item["product_id"],
    store__owner=seller,
    status=Product.Status.APPROVED,
)
unit_price=product.price  # SERVER AUTHORITY
```

**Why it works:** Price becomes a server-side invariant tied to catalog + seller.

**Status:** Fixed — `OrderLineCreateSerializer` accepts `product_id` + `quantity`; `OrderService._resolve_order_line()` loads catalog price

---

## C2. KYC / freeze bypass on orders and payments

**Severity:** Critical (BoZ KYC, FIC AML freeze)  
**OWASP:** A01 Broken Access Control  
**Files:** `apps/orders/views.py`, `apps/payments/views.py`, `apps/users/permissions.py`

**Issue:** `CanTransact` permission exists but is **never applied** to financial endpoints.

```python
# apps/orders/views.py
class OrderListCreateView(APIView):
    permission_classes = [IsAuthenticated]  # Missing CanTransact
```

```python
# apps/users/permissions.py — defined but unused on orders/payments
class CanTransact(BasePermission):
    def has_permission(self, request, view):
        return (
            user.is_authenticated
            and user.is_active
            and user.kyc_status == KYCStatus.VERIFIED
            and not user.is_frozen
        )
```

**Attack scenario:** `UNVERIFIED` or frozen user creates orders and initiates MoMo collections.

**Fix:**

```python
permission_classes = [IsAuthenticated, CanTransact]
# Apply to: orders create/submit, payments initiate, disputes, etc.
```

**Status:** Fixed — `CanTransact` on order create/submit, payments initiate, disputes; defense-in-depth in `OrderService.create_order`

---

## C3. Webhook signature bypass → forged payment success

**Severity:** Critical  
**OWASP:** A07 Identification and Authentication Failures  
**File:** `apps/payments/webhooks.py`

**Vulnerable code:**

```python
if not expected_token:
    return True  # Allow in development/sandbox without token

if sandbox:
    return True  # Airtel sandbox — skipping signature validation
```

**Attack scenario:** Misconfigured prod or sandbox mode allows forged `SUCCESS` webhooks → escrow hold without real MoMo debit.

**Fix:** Fail closed in production; validate `amount == PaymentAttempt.amount == order.total_amount`.

**Status:** Fixed — fail-closed when tokens/secrets missing (non-DEBUG); invalid signatures return 401; amount validated against order total

---

## C4. IDOR — cancel any user's order

**Severity:** Critical  
**OWASP:** A01 Broken Access Control  
**Files:** `apps/orders/views.py`, `apps/orders/services.py`

**Vulnerable code:**

```python
class OrderCancelView(APIView):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)  # No buyer/seller check
        OrderService.cancel_order(order=order, actor=request.user, ...)
```

**Attack scenario:** Attacker cancels victims' `DRAFT` / `PENDING_PAYMENT` orders.

**Fix:**

```python
if request.user not in (order.buyer, order.seller) and not request.user.is_staff:
    raise PermissionDenied()
```

**Status:** Fixed — `assert_order_party()` in views and `OrderService.cancel_order`

---

## C5. IDOR — complete any delivered order → release escrow

**Severity:** Critical  
**File:** `apps/orders/services.py`

**Issue:** `complete_order()` calls `EscrowService.release_funds()` with no check that `actor` is buyer, seller, or admin.

**Attack scenario:** Any authenticated user with a `DELIVERED` order UUID triggers escrow release.

**Fix:** Require `actor in (order.buyer, order.seller)` or `actor.is_staff`.

**Status:** Fixed — party check in `OrderService.complete_order`

---

## C6. Double MoMo charge after first successful payment

**Severity:** Critical  
**Files:** `apps/payments/tasks.py`, `apps/payments/views.py`, `apps/payments/services.py`

**Issue:**

- Payment success holds escrow but does not call `OrderService.confirm_payment()`
- Order stays `PENDING_PAYMENT`
- `initiate_collection` counts all attempts, not `SUCCESS` attempts

**Attack scenario:** Buyer pays 2–3 times for one order.

**Fix:** After webhook success, atomically confirm order + hold funds; block re-initiation if any `SUCCESS` attempt exists.

**Status:** Fixed — block re-collection after SUCCESS; `trigger_escrow_hold_on_payment_success` calls `OrderService.confirm_payment`

---

## C7. KYC object-key IDOR (identity document hijacking)

**Severity:** Critical  
**Files:** `apps/users/serializers.py`, `apps/users/services.py`

**Issue:** `KYCUploadSerializer` accepts arbitrary `nrc_front_key`, `nrc_back_key`, `selfie_key` without ownership validation.

**Attack scenario:** Attacker submits `kyc/<victim-uuid>/nrc_front_abc.jpg` → links victim's docs to attacker's account.

**Fix:** Validate keys match `kyc/{request.user.id}/`; use presigned upload URLs.

**Status:** Fixed — `validate_kyc_storage_key()` in serializer + service; multipart upload validation on `KYCUploadFileView`

---

# High Findings

## H1. Approved live listings editable without re-review

**Severity:** High  
**File:** `apps/products/views.py`

`VendorProductViewSet` has no `perform_update` override — DRF default allows PATCH of `price`, `name`, `description` on `APPROVED` products.

**Fix:** Route updates through `ProductService`; block sensitive fields or revert to `PENDING`.

**Status:** Fixed — `perform_update` blocks price/title/description on `APPROVED` products

---

## H2. Auth rate limiting ineffective

**Severity:** High  
**Files:** `config/settings/base.py`, `config/settings/prod.py`

Prod defines `"auth": "5/minute"` but `ScopedRateThrottle` is not in `DEFAULT_THROTTLE_CLASSES`. Login has no `throttle_scope`.

**Fix:** Add `ScopedRateThrottle`; set `throttle_scope = "auth"` on login/refresh.

**Status:** Fixed — `ScopedRateThrottle` in defaults; `throttle_scope = "auth"` on `LingiTokenObtainPairView`

---

## H3. Inconsistent admin authorization (`IsAdminUser` vs `IsAdmin`)

**Severity:** High  

Fraud/escrow/disputes use `IsAdminUser` (staff only). Users admin requires `is_staff AND role=ADMIN`.

**Fix:** Standardize on `IsAdmin` everywhere.

**Status:** Fixed — fraud, escrow, disputes, admin audit, products admin use `IsAdmin`

---

## H4. Unvalidated file uploads (KYC, disputes, product images)

**Severity:** High  

No file size limits, MIME validation, or extension allowlists. Dev serves media publicly when `DEBUG=True`.

**Fix:** Allowlist extensions; max 5–10 MB; private S3/R2 with signed URLs.

**Status:** Not fixed

---

## H5. Django admin 2FA not enforced

**Severity:** High  

`OTPMiddleware` installed but admin uses default site — no `OTPAdminSite`.

**Fix:** Switch to `django_otp.admin.OTPAdminSite`.

**Status:** Partial — KYC upload limits in `apps/core/upload_validators.py`; product/dispute uploads still need wiring

---

## H6. Orders ↔ Escrow API mismatch

**Severity:** High  

`OrderService` calls `EscrowService` with mismatched signatures. Ship/delivery does not sync escrow state.

**Fix:** Adapter layer + integration tests for full lifecycle.

**Status:** Fixed — `create_account`, `hold_funds`, `release_funds`, `refund` aligned; ship/delivery sync escrow via `mark_in_transit` / `mark_delivered`

---

## H7. JWT refresh token in `localStorage`

**Severity:** High  
**File:** `frontend/src/api/client.ts`

Refresh token stored in `localStorage` — XSS can steal long-lived sessions.

**Fix:** HttpOnly Secure cookies (BFF) or memory-only refresh + strict CSP.

**Status:** Not fixed

---

## H8. Admin user list — unbounded PII export

**Severity:** High  
**File:** `apps/users/views.py`

Returns all users with NRC, address, KYC metadata — no pagination, no audit log.

**Fix:** Paginate; list serializer without full PII; audit admin access.

**Status:** Not fixed

---

# Medium Findings

| # | Finding | Location | Status |
|---|---------|----------|--------|
| M1 | No inventory reservation on order submit | `apps/orders/services.py` | Not fixed |
| M2 | Admin cancel after payment without escrow refund | `apps/orders/services.py` | Not fixed |
| M3 | Partial refund logic broken | `apps/orders/services.py` | Not fixed |
| M4 | Double platform fee (order + escrow release) | orders + escrow | Not fixed |
| M5 | Collection attempt limit race | `apps/payments/services.py` | Not fixed |
| M6 | Redis idempotency never marked processed | `apps/payments/idempotency.py` | Not fixed |
| M7 | Registration phone not normalized before duplicate check | `apps/users/services.py` | Not fixed |
| M8 | `phone_verified` never enforced | users app | Not fixed |
| M9 | Password reset endpoints missing | `apps/users/urls.py` | Not fixed |
| M10 | Missing CSP / Referrer-Policy | `config/settings/prod.py` | Not fixed |
| M11 | Default DB password in repo | `base.py`, `docker-compose.yml` | Not fixed |
| M12 | Order list unpaginated | `apps/orders/views.py` | Not fixed |
| M13 | Enrichment errors leak internals | `apps/products/enrichment/` | Not fixed |
| M14 | Frozen user JWT valid on unprotected endpoints | JWT design | Not fixed |

---

# Low Findings

| # | Finding | Status |
|---|---------|--------|
| L1 | Fraud API returns exception strings to client | Not fixed |
| L2 | `INTERNAL_API_KEY` defined but unused | Not fixed |
| L3 | PII in registration logs | Not fixed |
| L4 | OpenAPI URL condition fragile | Not fixed |
| L5 | LLM SSRF if misconfigured `CATALOG_LLM_BASE_URL` | Not fixed |
| L6 | `OrderSubmitView` catches bare `Exception` | Not fixed |
| L7 | Staff can edit `is_superuser` in Django admin | Not fixed |

---

# E-Commerce Specific Review

## User Management

| Area | Status | Notes |
|------|--------|-------|
| Registration | Partial | Phone validation weak on serializer; duplicate check not normalized |
| Login | Partial | Frozen blocked at login; JWT remains valid elsewhere |
| Password reset | Missing | Frontend expects endpoints; backend not implemented |
| Email verification | N/A | Optional email only |
| MFA | Partial | OTP middleware present; admin 2FA not enforced |
| Account lockout | Missing | No login throttle scope |
| Session security | Partial | JWT in sessionStorage/localStorage |

## Vendor / Seller

| Area | Status | Notes |
|------|--------|-------|
| Vendor registration | OK | Store scoped to owner |
| Product ownership | OK | Queryset filtered by store |
| Store permissions | OK | `IsStoreApproved` enforced |
| Approved listing edits | **Vulnerable** | H1 — live price/description changes |

## Shopping Cart (Frontend)

| Area | Status | Notes |
|------|--------|-------|
| Price tampering | **Critical** | Server must ignore client prices (C1) |
| Quantity tampering | Partial | Frontend only; server must validate stock |
| Coupon/discount abuse | N/A | Not implemented |

## Orders & Payments

| Area | Status | Notes |
|------|--------|-------|
| Order ownership (read) | OK | Detail view checks buyer/seller |
| Order mutations | **Vulnerable** | Cancel/complete IDOR (C4, C5) |
| Payment webhooks | **Vulnerable** | Signature bypass (C3) |
| Double spending | **Vulnerable** | C6 |
| Webhook replay | Partial | DB constraints; idempotency incomplete |

---

# Database Audit

| Issue | Severity | Recommendation |
|-------|----------|----------------|
| Order list unpaginated | High at scale | Add pagination |
| Missing inventory reservation | Medium | `select_for_update` on submit |
| N+1 on product list | Medium | `prefetch_related("inventory")` (partially addressed) |
| Transaction safety on payments | High | Atomic order confirm + escrow hold |
| Dual dispute models | Low | Consolidate `OrderDispute` vs `disputes.Dispute` |

---

# API Security Review

| Check | Result |
|-------|--------|
| Broken authentication | Login OK; refresh in localStorage risky |
| Broken authorization | **Fail** on order mutations, KYC bypass |
| Excessive data exposure | Admin user list exports all PII |
| Mass assignment | Approved product PATCH |
| Rate limiting | **Misconfigured** |
| Input validation | File uploads weak; order lines weak |
| Pagination | Orders list missing |

---

# Performance Findings

| Issue | Impact | Fix |
|-------|--------|-----|
| Unpaginated order list | Memory/timeout at scale | PageNumberPagination |
| Admin user export (all rows) | Timeouts | Paginate + defer PII |
| Celery image enrichment without pixel cap | Worker OOM | `Image.MAX_IMAGE_PIXELS` |
| Checkout payment polling 5s | API load | Backoff or webhooks to client |

---

# Frontend Security Review

| Check | Result |
|-------|--------|
| DOM/stored XSS | No `dangerouslySetInnerHTML` found |
| Token leakage | Refresh in `localStorage` (H7) |
| Client-side auth only | Role checks in pages; server must enforce |
| Open redirects | Not observed |

**Fixes already applied (frontend page bugs, not security audit):**

- Checkout pickup/digital fulfilment
- Order totals from backend after create
- Payment retry without duplicate orders
- Disputes list from order disputes
- Real stock on catalogue (`is_in_stock`)
- Dynamic categories on home page
- Vendor pending-store messaging

---

# DevOps & Infrastructure Review

| Item | Prod | Dev | Recommendation |
|------|------|-----|----------------|
| `DEBUG` | False | True | Never deploy dev settings |
| HSTS / secure cookies | Yes | No | OK for prod |
| CSP | Missing | Missing | Add in prod + nginx |
| Default DB password | In repo | In compose | Require env vars |
| Postgres/Redis exposed | — | Ports 5432/6379 | Bind to 127.0.0.1 |
| Docker non-root user | Yes | Yes | Good |
| Sentry PII | Disabled | — | Good |

---

# Code Quality Findings

**Strengths:**

- Thin views → service layer
- State machines for orders/escrow/products
- Vendor queryset scoping
- Custom exception handler

**Weaknesses:**

- Permissions defined but not applied (`CanTransact`)
- Two dispute systems
- Cross-app signature mismatches (orders/escrow/payments)

---

# Testing Review

**Present:** Unit tests for orders, products, escrow, payments, enrichment.

**Missing (critical):**

- Price tampering rejected
- Unverified user cannot create order
- User A cannot cancel User B's order
- Webhook without signature rejected in prod
- Second payment blocked after SUCCESS
- Approved product price PATCH rejected

---

# Recommended Fix Priority

1. Server-side pricing (C1)
2. Wire `CanTransact` (C2)
3. Fail-closed webhooks + amount validation (C3)
4. Party authorization on all order views (C4, C5)
5. Payment success → confirm order; block duplicates (C6)
6. KYC key validation (C7)
7. File upload hardening (H4)
8. Approved product edit lock (H1)
9. Rate limiting (H2)
10. Unify `IsAdmin` (H3)
11. Escrow adapter alignment (H6)
12. Token storage + CSP (H7, M10)

---

# Secure Refactored Patterns

### Transactional API base

```python
from apps.users.permissions import CanTransact
from rest_framework.permissions import IsAuthenticated

class TransactionalAPIView(APIView):
    permission_classes = [IsAuthenticated, CanTransact]
```

### Order party check

```python
if request.user not in (order.buyer, order.seller) and not request.user.is_staff:
    raise PermissionDenied()
```

### Production webhook guard

```python
if not settings.DEBUG and not validator(request):
    return JsonResponse({"status": "rejected"}, status=403)
```

---

# Production Deployment Checklist

### Security (must fix before launch)

- [ ] Server-side pricing enforced (C1)
- [ ] `CanTransact` on all payment/order endpoints (C2)
- [ ] Webhook signatures fail-closed in prod (C3)
- [ ] Order party checks on cancel/complete/ship/dispute (C4, C5)
- [ ] Duplicate payment prevention (C6)
- [ ] KYC upload key validation (C7)
- [ ] File upload size + type restrictions (H4)
- [ ] Approved listing edit policy (H1)
- [ ] Login rate limiting (H2)
- [ ] Admin 2FA (H5)
- [ ] Refresh tokens not in localStorage (H7)
- [ ] CSP + Referrer-Policy (M10)
- [ ] `DEBUG=False`, no public KYC media
- [ ] Secrets only in env/secrets manager
- [ ] DB/Redis not on public interfaces

### Compliance (Zambia)

- [ ] KYC before MoMo collection
- [ ] Frozen account blocks all transactions
- [ ] Admin PII access audited

### CI tooling

```bash
bandit -r apps/ -ll
semgrep --config=p/owasp-top-ten apps/ frontend/src/
pip-audit -r requirements/base.txt
python manage.py check --deploy --settings=config.settings.prod
npm audit --prefix frontend
```

---

# Positive Security Controls (Already in Place)

- JWT refresh rotation + blacklist
- Frozen users blocked at login
- Vendor products scoped via `store=request.user.store`
- Payment status polling scoped to `initiated_by=request.user`
- Prod: HSTS, secure cookies, SSL redirect, signed S3 URLs
- Webhook payload size limit (64KB)
- Constant-time HMAC for MTN callback token
- Non-root Docker user
- Escrow admin views read-only staff-only

---

# Appendix: Files Reviewed

- `config/settings/` (base, dev, prod, test)
- `config/urls.py`, `config/celery.py`
- `apps/users/` — auth, KYC, permissions
- `apps/orders/` — views, services, serializers
- `apps/payments/` — webhooks, services, idempotency
- `apps/escrow/` — services, state machine
- `apps/products/` — views, permissions, enrichment, uploads
- `apps/disputes/`, `apps/fraud/`, `apps/logistics/`
- `frontend/src/` — API client, pages, store
- `docker-compose.yml`, `Dockerfile`, `requirements/`

---

*End of report. For remediation implementation, open an Agent task: "Implement P0 security fixes from docs/SECURITY_AUDIT.md".*
