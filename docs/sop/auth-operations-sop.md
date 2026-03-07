# Auth and RBAC Operations SOP

## Purpose
Defines the operational backend flow for authentication, admin-controlled user lifecycle management, role maintenance, and module-access governance.

## Preconditions
- Admin token is required for user creation, role maintenance, and role-module assignment.
- Local users must exist before login can succeed.
- Users attached to inactive roles are considered unauthorized.

## Standard Flow
1. Admin creates a user with `POST /api/v1/users/`.
2. User logs in with `POST /api/v1/auth/login`.
3. Client reads current identity with `GET /api/v1/auth/me`.
4. Client rotates refresh tokens with `POST /api/v1/auth/refresh`.
5. Client revokes refresh tokens with `POST /api/v1/auth/logout` or `POST /api/v1/auth/logout-all`.
6. User changes password with `POST /api/v1/auth/change-password` when authenticated.
7. Password recovery uses:
   - `POST /api/v1/auth/forgot-password`
   - `POST /api/v1/auth/reset-password`
8. Admin manages roles with:
   - `GET /api/v1/roles/`
   - `POST /api/v1/roles/`
   - `PUT /api/v1/roles/{role_id}`
   - `DELETE /api/v1/roles/{role_id}`
9. Admin assigns module access with:
   - `GET /api/v1/roles/{role_id}/modules`
   - `PUT /api/v1/roles/{role_id}/modules`
10. Admin manages user state with:
   - `GET /api/v1/users/`
   - `POST /api/v1/users/{user_id}/unlock`
   - `POST /api/v1/users/{user_id}/disable`
   - `POST /api/v1/users/{user_id}/enable`
   - `POST /api/v1/users/{user_id}/soft-delete`
   - `DELETE /api/v1/users/{user_id}`

## Control Rules
- There is no public user-registration API.
- Only Admin can create users, create roles, update roles, deactivate roles, or assign module access.
- Only Admin can change another user's role, active state, or lock state.
- Non-admin users can only read and update their own user record.
- Role deactivation blocks future authentication and protected API access for users assigned to that role.
- `role_module_access` overrides single-role naming and allows admin-approved multi-module access.
- `Admin` bypasses module restrictions, but still requires an active role and active user state.

## Validation Checklist
- Anonymous `POST /api/v1/users/` must return `401`.
- Non-admin attempt to create an Admin user must return `403`.
- Non-admin attempt to update another user must return `403`.
- Non-admin attempt to set `role_id`, `is_active`, or `is_locked` must return `403`.
- User with inactive role must fail login and protected route access.
- Module-assigned custom roles must be denied before assignment and allowed after admin assignment.

## Module Access Notes
- Current business module keys include `sales`, `purchase`, `stores`, `engineering`, and `production`.
- Placeholder module keys also exist for `quality`, `maintenance`, and `dispatch`, but access becomes meaningful only when those routers are implemented.
- `users` and `roles` remain admin-governed APIs, not business-module self-service APIs.

## Traceability
- Authentication, user administration, role updates, and role-module updates are audit logged.
- Refresh-token rotation and revocation provide session-level traceability.
