# Authentication and Account Recovery

This application now supports self-service registration and password reset
workflows that complement the existing session-based authentication.

## User registration

* **Endpoint:** `POST /api/auth/register`
* **Request body:**
  * `username` – 3 to 80 characters, case-insensitive uniqueness enforced.
  * `email` – valid email address, stored in the database for future recovery
    requests (case-insensitive uniqueness enforced).
  * `password` – minimum 8 characters; hashed with bcrypt before storage.
* **Response:**
  * `{ "message": string, "expires_at": ISO timestamp }`
  * `expires_at` indicates when the onboarding token will expire.
* **Side effects:**
  * Inserts the new user into the `users` table with a hashed password.
    * Generates an onboarding token, persists a hashed copy in the
    `user_tokens` table (type `onboarding`), and queues a background task that
    logs the simulated onboarding email with token and expiry. The email sender
    defaults to `noreply@example.com` and is configurable.
  * Enforces uniqueness on both username and email (case-insensitive for email).

If a duplicate username or email is submitted, the endpoint returns a `400`
error detailing which value conflicts. Validation errors from Pydantic are
returned with a `422` status.

## Password reset

* **Endpoint:** `POST /api/auth/password-reset`
* **Request body:**
  * `identifier` – the username or email associated with the account. Lookups
    are case-insensitive.
* **Response:**
  * `{ "message": string, "expires_at": ISO timestamp }`
  * The response is the same regardless of whether a matching account exists to
    avoid disclosing account existence.
* **Side effects:**
  * When a matching user with an email is found, the service generates a
    password reset token, persists a hashed copy in the `user_tokens` table
    (type `password_reset`) with an expiry, and logs a simulated email
    containing the reset instructions.
  * If a user is found without an email on file, a warning is logged.

Tokens are retained in the database until they expire (or are consumed),
allowing verification even after an application restart. Only SHA-256 hashes of
the tokens are stored; the plaintext value is sent via email and returned to the
caller when issued.

## Environment configuration

The following environment variables influence the new flows (all optional):

| Variable | Description | Default |
| --- | --- | --- |
| `ONBOARDING_TOKEN_TTL_MINUTES` | Lifetime in minutes for onboarding tokens. | `2880` (48 hours) |
| `PASSWORD_RESET_TOKEN_TTL_MINUTES` | Lifetime in minutes for password reset tokens. | `60` |
| `AUTH_TOKEN_BYTES` | Number of random bytes used when generating tokens (`secrets.token_urlsafe`). | `32` |
| `EMAIL_SENDER` | Logical sender displayed in logged email notifications. | `noreply@example.com` |

## Frontend experience

The React application exposes the new flows via dedicated screens:

* `/register` for account creation with inline validation and success/error
  messaging.
* `/forgot-password` for requesting a reset link.
* Updated navigation and login pages link to the new flows. Login now accepts a
  username **or** email address.

Successful actions display confirmation messages including token expiry details,
mirroring the responses from the backend.