# Minimal Django API Additions Required for Flutter MVP

## Current state
- Django project includes domain models and admin/server-rendered views.
- `rest_framework` is installed but no REST endpoints are exposed.

## Proposed minimal API (v1)
Base: `/api/v1`

### 1) Auth
- `POST /auth/login/`
  - body: `{ "username": "...", "password": "..." }`
  - response: `{ "access": "token", "user": {"id":1,"username":"...","role":"admin"} }`
- `POST /auth/logout/` (optional if token blacklist used)
- `GET /auth/me/`

### 2) Dashboard
- `GET /dashboard/summary/`
  - response fields:
    - `active_rentals`
    - `monthly_revenue`
    - `outstanding_balances`

### 3) Vehicles
- `GET /vehicles/` (supports `search`, `status`, `page`)
- `GET /vehicles/{id}/`
- `GET /vehicles/availability/?start_date=&end_date=` (optional for create form UX)

### 4) Rentals
- `GET /rentals/` (supports `status`, `customer`, `vehicle`, `page`)
- `GET /rentals/{id}/`
- `POST /rentals/`
  - required: `customer_id`, `vehicle_id`, `branch_id`, `start_date`, `end_date`, `daily_rate`
  - optional: `traffic_fines`, `vat_percentage`, `notes`

### 5) Supporting lookup endpoints
- `GET /customers/` (id, full_name)
- `GET /branches/` (id, name)

## Auth recommendation
- Prefer DRF SimpleJWT (`Bearer` token) for mobile apps.

## Validation requirements for `POST /rentals/`
- Vehicle must be available in selected period.
- `end_date` > `start_date`.
- Auto-calculate totals server-side from rental model logic.

## Non-breaking implementation note
- Add these APIs under new `api/` Django app or `apps/*/api.py` modules.
- Keep existing admin and template routes unchanged.
