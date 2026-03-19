/**
 * Auth API Contracts — Inspire Genius Backend
 *
 * Shared type definitions for multi-role authentication.
 * These types are the source of truth consumed by the frontend.
 */

export type UserRole =
  | "user"
  | "super-admin"
  | "coach-admin"
  | "org-admin"
  | "prompt-engineer";

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  avatarUrl?: string;
}

export interface LoginResponse {
  success: boolean;
  data: {
    user: AuthUser;
    tokens: {
      accessToken: string;
      refreshToken: string;
    };
  };
}

export interface RegisterRequest {
  email: string;
  password: string;
  confirm_password: string;
  role?: UserRole; // defaults to "user"
}

export interface RefreshTokenResponse {
  success: boolean;
  data: {
    access_token: string;
    id_token: string;
    token_type: string;
    expires_in: number;
    role: UserRole;
  };
}

export interface MeResponse {
  status: boolean;
  message: string;
  data: {
    user_id: string;
    email: string;
    full_name: string | null;
    first_name: string | null;
    last_name: string | null;
    role: UserRole | null;
    organization_id: string | null;
    business_id: string | null;
    is_onboarded: string;
    has_profile: boolean;
    password_change_allowed: boolean;
  };
}

export interface ChangeRoleRequest {
  role: UserRole;
}

export interface ChangeRoleResponse {
  status: boolean;
  message: string;
  data: {
    user_id: string;
    previous_role: UserRole;
    new_role: UserRole;
  };
}
