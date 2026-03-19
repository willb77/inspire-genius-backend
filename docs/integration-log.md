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
