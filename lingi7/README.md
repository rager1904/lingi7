# Lingi7

**Fintech-grade escrow & AI-powered e-commerce platform for Zambia.**

Secure transactions, real-time supply chain tracking, and automated dispute resolution — built for Zambia, scalable across SADC.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django 4.2 + Django REST Framework |
| Database | PostgreSQL 15 (isolated escrow_ledger schema) |
| Cache / Queue | Redis 7 + Celery |
| Payments | MTN Mobile Money + Airtel Money |
| ML | Python · scikit-learn · XGBoost |
| Frontend | React 18 + TypeScript |
| Infrastructure | Docker · Nginx · Cloudflare |

---

## Quick Start (Local Development)

### Prerequisites
- Docker Desktop
- Python 3.11+
- Git

### Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd lingi7

# 2. Copy and configure environment variables
cp .env.example .env.dev
# Edit .env.dev — fill in SECRET_KEY and any API credentials

# 3. Start all services
make up

# 4. Apply migrations
make migrate

# 5. Create a superuser for the admin panel
make createsuperuser

# 6. Visit the admin panel
open http://localhost:8000/admin/

# 7. Visit the API docs
open http://localhost:8000/api/schema/swagger/
```

### Common Commands

```bash
make up           # Start all Docker services
make down         # Stop all services
make logs         # Tail all service logs
make shell        # Django shell_plus (interactive)
make test         # Run full test suite with coverage
make lint         # Run flake8 + bandit
make fmt          # Auto-format with black + isort
make migrate      # Apply database migrations
make reset-db     # Wipe and recreate dev database (DESTRUCTIVE)
```

---

## Project Structure

```
lingi7/
├── config/             # Django settings, Celery, URLs
│   └── settings/       # base.py, dev.py, prod.py, test.py
├── apps/               # All Django application modules
│   ├── users/          # Auth, KYC — P0
│   ├── admin_audit/    # Immutable audit log — P0
│   ├── escrow/         # Core escrow ledger — P0 [BUILD FIRST]
│   ├── payments/       # MTN MoMo + Airtel — P0
│   ├── orders/         # Order lifecycle — P0
│   ├── fraud/          # Fraud rule engine — P0
│   ├── logistics/      # Shipment tracking — P0
│   ├── disputes/       # Dispute resolution — P1
│   └── products/       # Product catalogue — P1
├── ml/                 # ML training pipelines
├── tests/              # Integration tests
├── infra/              # Nginx, scripts, DB init
├── frontend/           # React + TypeScript (Phase 1)
└── docs/               # Architecture, API, compliance docs
```

---

## Regulatory Compliance (Zambia)

- **Data Protection Act 2021** — registered as Data Controller before collecting user data
- **Bank of Zambia KYC** — NRC verification required for all users
- **ZICTA E-Commerce Rules** — refund policy, merchant disclosure, complaint resolution
- **ZRA** — VAT registration when revenue exceeds ZMW 800,000/year
- **FIC AML** — transaction monitoring thresholds enforced

---

## Architecture Principles

1. **Escrow integrity is non-negotiable.** All fund movements use `select_for_update()` + `transaction.atomic()`. Every debit has a paired credit. No exceptions.
2. **Fat services, thin views.** Business logic lives in `services.py`. Views only validate input and call services.
3. **Every admin action is audited.** `AdminAuditLog` captures before/after state on every change.
4. **Fraud gate before every release.** No escrow RELEASED transition without passing the fraud pipeline.
5. **Tests are not optional.** 80% coverage minimum enforced in CI. Escrow and payment code requires 100% branch coverage.

---

## Environment Variables

See `.env.example` for a complete list of all required variables with documentation.

**Never commit `.env` files or secrets to git.**

---

*Build with integrity. Ship with urgency. Document everything.*
