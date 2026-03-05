
## 1. User Registration

## 2. User Login

## 3. Password Reset

## 4. Role Assignment

## 5. Deactivation/Obsolescence

## 6. Security Best Practices


# Auth Module - Standard Operating Procedures (SOP)

## Purpose
Defines the standard API and process flow for user authentication, registration, password management, and role control with audit and security best practices.

## Preconditions
- User must provide valid credentials for login.
- Admin role required for user/role management APIs.

## Standard Flow
1. **User Registration** (`POST /api/v1/auth/register`)
	- Required: username, email, password, role
	- Validates email format and password strength
	- Sends verification email if enabled
2. **User Login** (`POST /api/v1/auth/login`)
	- Accepts username/email and password
	- Locks account after repeated failed attempts (if configured)
	- Logs all login attempts for audit
3. **Password Reset**
	- Request: `POST /api/v1/auth/password-reset-request` (email required)
	- Reset: `POST /api/v1/auth/password-reset` (token, new password)
	- Uses secure, time-limited reset tokens
	- Logs all password reset requests and completions
4. **Role Assignment** (`POST /api/v1/auth/assign-role`)
	- Admin assigns/removes roles
	- Enforces least-privilege principle
	- Logs all role changes for traceability
5. **Deactivation/Obsolescence** (`PATCH /api/v1/auth/deactivate`)
	- Deactivates users instead of deleting
	- Marks obsolete users and restricts access
	- Maintains audit trail of all user status changes

## Control Rules
- Only Admin can assign/remove roles or deactivate users.
- Password reset tokens expire after set duration.
- Deactivated users cannot log in.
- All status changes and logins are audit-logged.

## Validation Checklist
- Registration rejects missing/invalid email or weak password.
- Login rejects invalid credentials and logs attempt.
- Password reset rejects expired/invalid tokens.
- Role assignment rejects unauthorized requests.
- Deactivation blocks login and API access for user.

## Security & Traceability
- Enforce strong password policies and MFA if available.
- Regularly review user and role lists.
- All critical actions (register, login, reset, role change, deactivate) are logged with timestamp and user ID for traceability.
