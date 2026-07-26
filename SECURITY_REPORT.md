Copyright © 2026 Francis Banda.
All Rights Reserved.

This software and all associated intellectual property are proprietary and owned exclusively by Francis Banda.

Unauthorized copying, modification, distribution, sublicensing, resale, reverse engineering, or commercial use is prohibited without explicit written permission from Francis Banda.

# Security Report

## Summary

The platform has a solid Django security baseline for the core app, including JWT auth, CSRF middleware, password validators, throttling, 2FA middleware for admin, secure production cookie settings, HSTS, and DRF permissions. The highest risk remains the AI service boundary: enrichment and assistant need stronger authentication, CORS restrictions, upload validation, and observability before production exposure.

## Fixed During This Audit

- Removed unsafe root compose defaults for database password, API key, Django secret key, Hugging Face token, and MinIO credentials.
- Fixed `.env.example` to document the actual `SECRET_KEY` consumed by Django.
- Enabled `/health/` route for dependency monitoring.
- Disabled Nginx version disclosure with `server_tokens off`.
- Aligned Nginx API gateway route with Django `/api/v1/`.

## Findings

| Severity | Finding | Impact | Recommendation |
| --- | --- | --- | --- |
| High | AI services can be reached through Nginx routes without Django JWT enforcement | Unauthorized users may call expensive or sensitive AI workflows | Put user-facing AI calls behind Django `/api/v1/ai/*` or enforce gateway JWT validation |
| High | Assistant CORS allows `*` with credentials enabled | Browser-based cross-origin abuse risk | Replace with environment-controlled allowlist |
| High | Upload validation in enrichment trusts content type and lacks image size cap | DoS and malicious file upload risk | Enforce byte limits, extension allowlist, magic-byte validation, and malware scanning |
| Medium | Root compose requires GPU/gated models but lacks resource profiles | Misconfigured deployments may partially start or leak errors | Add dev/prod compose profiles and startup validation |
| Medium | Mojibake in config comments/docs | Operational errors from misunderstood docs | Normalize file encoding to UTF-8 in a dedicated cleanup pass |
| Medium | No discovered CI secret scanning/dependency scanning workflow | Regressions may ship | Add GitHub Actions or equivalent for tests, Bandit, pip-audit, npm audit, and secret scanning |
| Low | API docs enabled whenever `DEBUG` is true | Acceptable for dev, unsafe if debug misconfigured | Ensure production environment forces `DEBUG=False` and blocks docs at proxy/WAF |

## OWASP Review

| Category | Status |
| --- | --- |
| Authentication | Strongest in Django; incomplete in AI services |
| Authorization | DRF permissions present; AI mutation flows must route through Django |
| Input validation | Good in some serializers; enrichment upload path needs hardening |
| CSRF | Django middleware enabled; JWT APIs still need careful browser storage strategy |
| XSS | React mostly escapes by default; assistant contains `SafeHTML` component that requires careful sanitization review |
| SQL injection | Django ORM usage lowers risk; raw SQL found in health check only (`SELECT 1`) |
| SSRF | Model and callback URLs must be environment allowlisted |
| Secrets exposure | Root defaults fixed; verify no real `.env` files are committed |
| File uploads | KYC and enrichment uploads require strict validation and private storage |

## Required Before Production

- Enforce authenticated AI access.
- Add internal service authentication and request signing.
- Add upload scanner and strict size/type checks.
- Add dependency and secret scanning CI.
- Add security headers for all frontend routes.
- Rotate any credentials if default MinIO or database values were ever used.
# eCommerce Security Report Update

Copyright © 2026 Francis Banda.  
All Rights Reserved.

This platform, source code, architecture, workflows, models, databases, documentation, and all associated intellectual property are proprietary and exclusively owned by Francis Banda.

## Implemented Controls

- Unified JWT authentication through Django SimpleJWT.
- `/api/v1/ai/assistant/query/` requires authentication.
- AI search and assistant endpoints use DRF scoped throttling.
- Product search returns only approved products from approved stores.
- Vendor enrichment and image operations remain scoped through existing vendor permissions.
- Internal AI services are designed to sit behind Django/nginx, not direct public exposure.
- Docker secrets now require explicit environment values instead of unsafe defaults.
- Nginx has `server_tokens off` and forwards `/api/v1`.

## Findings Fixed

- Removed NVIDIA hosted endpoints and GPU runtime assumptions.
- Removed active NVIDIA branding/font calls from assistant UI.
- Removed enrichment UI dependency on bundled NVIDIA Kaizen package.
- Added database fallback paths so AI service outages do not create unsafe failure states.

## Remaining Security Work

- Run full dependency vulnerability scans after installing assistant/enrichment UI dependencies.
- Add signed internal-service headers if AI services are exposed outside the Docker network.
- Add request body size limits for assistant image requests at nginx and Django.
- Add audit events for assistant/enrichment calls that mutate product-visible fields.
