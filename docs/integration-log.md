# Integration Log

## 2026-03-19

READY FOR INTEGRATION: ws-c/foundation — Deliverable 1.1 Multi-Role Auth API

### What changed
- Added `require_role(*allowed_roles)` decorator — flexible role guard replacing per-role decorators
- Extended `VALID_ROLES` set: `user`, `super-admin`, `coach-admin`, `org-admin`, `prompt-engineer`, `admin`
- `POST /v1/signup` now accepts optional `role` field (defaults to `"user"`)
- `POST /v1/refresh-token` response now includes `role` field
- `PUT /v1/user-management/users/{user_id}/role` — super-admin-only endpoint to change user roles
- Alembic migration seeds all required roles in `roles` table and adds `ix_roles_name` index
- API contract types in `docs/api-contracts/auth.ts`
- Tests in `tests/test_multi_role_auth.py`

### Integration notes for WS-A (Frontend)
- Login response already includes `role` — no change needed
- Frontend should use the `UserRole` type union from `docs/api-contracts/auth.ts`
- New roles can be used with `ProtectedRoute` component's role checks
- Role change endpoint: `PUT /v1/user-management/users/{user_id}/role` with body `{ "role": "coach-admin" }`

## 2026-03-20

READY FOR INTEGRATION: ws-c/phase-2 — Deliverables 2.1–2.4 Multi-Role API Endpoints

### What changed
- **VALID_ROLES** updated to 6 canonical roles: `user`, `manager`, `company-admin`, `practitioner`, `distributor`, `super-admin`
- **UserRole** type in `docs/api-contracts/auth.ts` updated to match
- **12 new database tables** via Alembic migration: training_assignments, hiring_positions, candidates, interviews, practitioner_clients, coaching_sessions, practitioner_credits, follow_ups, distributor_territories, distributor_practitioners, distributor_credits, credit_transactions
- **4 new route modules** registered in main.py:
  - `GET/POST /v1/managers/:id/*` — 6 endpoints (team, activity, training, hiring, interviews, invite)
  - `GET/POST/PUT/DELETE /v1/company-admin/*` — 8 endpoints (users CRUD, settings, analytics, costs)
  - `GET/POST /v1/practitioners/:id/*` — 6 endpoints (clients, sessions, credits, followups, dashboard)
  - `GET/POST /v1/distributors/:id/*` — 6 endpoints (practitioners, credits, allocate, transactions, territory)
- All endpoints enforce role-based access via `require_role()` decorator
- Tests in `tests/test_phase2_role_endpoints.py`

### Integration notes for WS-A (Frontend)
- All endpoints use the standard response envelope (`status`, `message`, `error_status`, `data`)
- Manager endpoints at `/v1/managers/{manager_id}/...`
- Company Admin endpoints at `/v1/company-admin/...`
- Practitioner endpoints at `/v1/practitioners/{practitioner_id}/...`
- Distributor endpoints at `/v1/distributors/{distributor_id}/...`
