# Changelog

## 2026-03-01 — Phase-1 Validation & Hardening

### Added
- User management enhancements:
  - Admin user list filters (`username`, `role`, `is_locked`, `auth_provider`) with pagination support.
  - Admin actions: unlock user, disable user, enable user.
  - Soft-delete endpoint support for users.
- Test coverage for new user filters and admin user-state endpoints.

### Changed
- Role read endpoints (`list`, `get`) now require admin authorization for strict role CRUD governance.
- Configuration defaults hardened to avoid sensitive hardcoded values in source.

### Security
- Secrets and environment-specific credentials are expected from `.env`; `.env.example` remains the template.
- Existing auth capabilities retained and validated: JWT access/refresh, local+Google auth support, account lockout controls, password reset flow.

### Validation
- Full test suite status after validation/fixes: `34 passed`.

### Notes
- This release finalizes Phase-1 backend validation and stabilization.
- Phase-2 work has not started in this release.
