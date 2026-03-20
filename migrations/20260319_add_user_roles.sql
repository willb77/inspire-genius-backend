-- Migration: Add multi-role authentication support
-- Date: 2026-03-19
-- Description: Seeds new role entries and adds index on roles.name

-- 1. Add index on roles.name for faster lookups
CREATE INDEX IF NOT EXISTS ix_roles_name ON roles (name);

-- 2. Seed required roles (idempotent — skips existing)
INSERT INTO roles (id, name, role_level, is_deleted, created_at)
SELECT gen_random_uuid(), 'user', 'SYSTEM', false, NOW()
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE LOWER(name) = 'user');

INSERT INTO roles (id, name, role_level, is_deleted, created_at)
SELECT gen_random_uuid(), 'super-admin', 'SYSTEM', false, NOW()
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE LOWER(name) = 'super-admin');

INSERT INTO roles (id, name, role_level, is_deleted, created_at)
SELECT gen_random_uuid(), 'coach-admin', 'SYSTEM', false, NOW()
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE LOWER(name) = 'coach-admin');

INSERT INTO roles (id, name, role_level, is_deleted, created_at)
SELECT gen_random_uuid(), 'org-admin', 'SYSTEM', false, NOW()
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE LOWER(name) = 'org-admin');

INSERT INTO roles (id, name, role_level, is_deleted, created_at)
SELECT gen_random_uuid(), 'prompt-engineer', 'SYSTEM', false, NOW()
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE LOWER(name) = 'prompt-engineer');

-- Verify: existing users without a role in user_profiles default to "user"
-- (No-op: the application code defaults new signups to "user" role already.
--  Existing users will continue to work via the Cognito role fallback.)
