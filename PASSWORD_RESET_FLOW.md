# Password Reset Flow

Base URL: `http://localhost:8000/api`

---

## Overview

Two steps:

1. User submits their email → backend sends a reset link to that email.
2. User clicks the link → frontend reads the token from the URL and POSTs it with a new password.

---

## Step 1 — Request Reset Email

```http
POST /api/auth/password/reset/
Content-Type: application/json
```

### Request body

```json
{
  "email": "user@example.com"
}
```

### Response `200`

```json
{
  "detail": "If that email is registered, a reset link has been sent."
}
```

> This response is always the same whether or not the email exists. Do not try to infer user existence from it.

### Validation error

```json
{
  "email": ["This field is required."]
}
```

---

## Step 2 — Confirm Reset

The email contains a link to:

```text
{FRONTEND_URL}/reset-password?token=<token>
```

Read `token` from the query string and POST it along with the new password.

```http
POST /api/auth/password/reset/confirm/
Content-Type: application/json
```

### Request body

```json
{
  "token": "<token from URL query string>",
  "new_password1": "<new password>",
  "new_password2": "<new password>"
}
```

### Response `200`

```json
{
  "detail": "Password reset complete. You can now log in."
}
```

After a successful reset, redirect the user to the login page. No auth token is returned.

### Validation errors

| Field | Message | Cause |
| --- | --- | --- |
| `token` | `This reset link is invalid or has expired.` | Token not found, already used, or older than 1 hour |
| `new_password2` | `The two password fields did not match.` | `new_password1` and `new_password2` differ |
| `new_password1` | `This password is too short. It must contain at least 8 characters.` | Password under 8 characters |
| `token` | `This field is required.` | Token missing from request |
| `new_password1` | `This field is required.` | Password missing from request |

---

## Frontend Implementation Notes

- Token expires after **1 hour**.
- A token is **single-use** — submitting it a second time returns the invalid/expired error.
- Passwords must pass Django's validators: at least **8 characters**, not a common password, not entirely numeric, not too similar to the user's name/email. Show the server's `new_password1` messages.
- Requesting a new link invalidates any earlier unused link.
- A successful reset signs the user out of **every** existing session.
- Only a SHA-256 hash of the token is stored, so links cannot be recovered from the database.
- Reset requests are limited to 5/minute per IP and 5/hour per email (`429` beyond that).
- Always show the same message on the request form regardless of whether the email was found ("Check your email if it's registered").
- Parse the token with `new URLSearchParams(window.location.search).get('token')` or your router's query param utility.
- If the confirm request returns a token error, show an "expired or invalid link" message with a prompt to request a new one.