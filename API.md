# EventLight API Documentation

**Base URL (dev):** `http://localhost:8000/api`  
**Auth scheme:** Token — `Authorization: Token <token>`  
**Content type:** `application/json` for all requests unless uploading a file (see [Images](#images))

---

## Table of Contents

1. [Conventions](#conventions)
2. [Authentication](#authentication)
   - [Register](#register)
   - [Login](#login)
   - [Logout](#logout)
   - [Current User](#current-user)
   - [Change Password](#change-password)
   - [Forgot Password](#forgot-password)
3. [Categories](#categories)
4. [Events](#events)
   - [List Events](#list-events)
   - [Create Event](#create-event)
   - [Get Event](#get-event)
   - [Update Event](#update-event)
   - [Delete Event](#delete-event)
   - [Related Events](#related-events)
   - [Personal Collections](#personal-collections)
5. [Likes & Saves](#likes--saves)
6. [RSVP & Attendance](#rsvp--attendance)
7. [Notifications](#notifications)
8. [Public Users](#public-users)
9. [Images](#images)
10. [Enumerations](#enumerations)
11. [Error Reference](#error-reference)

---

## Conventions

### Timestamps

All timestamps are ISO 8601 UTC strings:

```
2026-12-01T09:00:00Z
```

### Authentication

Protected endpoints require:

```http
Authorization: Token <token>
```

Some endpoints are **auth-aware**: they work without a token but return extra user-specific fields (`is_liked`, `is_saved`, `is_rsvped`) when a valid token is provided.

### Response shapes

**Success** — `200` or `201`, body varies per endpoint.

**General error:**

```json
{ "detail": "Error message here." }
```

**Validation error:**

```json
{
  "field_name": ["Error message."],
  "another_field": ["Another error."]
}
```

**Paginated list:**

```json
{
  "count": 143,
  "next": "http://localhost:8000/api/events/?page=2",
  "previous": null,
  "results": []
}
```

Pagination defaults: `page_size=12`, max `page_size=50`. Pass `?page=N&page_size=N` to override.

**Flat array** (personal collections, categories): root-level JSON array, no pagination wrapper.

---

## Authentication

### Register

```http
POST /api/auth/register/
```

**Request:**

```json
{
  "email": "user@example.com",
  "password": "password123",
  "first_name": "Desmond",
  "last_name": "Egya",
  "username": "desmond_e"
}
```

| Field | Required | Notes |
|---|---|---|
| `email` | Yes | Must be unique |
| `password` | Yes | Min 8 characters |
| `first_name` | No | |
| `last_name` | No | |
| `username` | No | Defaults to email if omitted |

**Response `201`:**

```json
{
  "key": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "first_name": "Desmond",
    "last_name": "Egya",
    "username": "desmond_e",
    "phone_number": "",
    "street_address": "",
    "city": "",
    "state": "",
    "country": "Nigeria",
    "preferred_categories": [],
    "preferred_languages": [],
    "preferred_age_groups": [],
    "max_distance_km": null,
    "email_notifications": true,
    "event_reminders": true,
    "date_joined": "2026-05-09T12:00:00Z",
    "events_created_count": 0,
    "events_liked_count": 0,
    "events_saved_count": 0,
    "events_attending_count": 0
  }
}
```

**Errors:**

```json
{ "email": ["A user with this email already exists."] }
{ "password": ["This password is too short. It must contain at least 8 characters."] }
```

---

### Login

```http
POST /api/auth/login/
```

**Request:**

```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

**Response `200`:**

```json
{
  "key": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b",
  "user": { "...": "full user object" }
}
```

**Error:**

```json
{ "detail": "Invalid credentials." }
```

---

### Logout

```http
POST /api/auth/logout/
Authorization: Token <token>
```

Invalidates the current token. No request body needed.

**Response `200`:**

```json
{ "detail": "Logged out successfully." }
```

---

### Current User

```http
GET  /api/auth/user/
PATCH /api/auth/user/
Authorization: Token <token>
```

`GET` returns the full user object.

`PATCH` accepts any subset of updatable fields and returns the full updated user object:

```json
{
  "first_name": "Desmond",
  "last_name": "Egya",
  "username": "desmond_e",
  "phone_number": "+234 800 000 0000",
  "street_address": "12 Church Street",
  "city": "Lagos",
  "state": "Lagos State",
  "country": "Nigeria",
  "preferred_categories": ["worship", "music"],
  "preferred_languages": ["english", "yoruba"],
  "preferred_age_groups": ["young_adults"],
  "max_distance_km": 50,
  "email_notifications": true,
  "event_reminders": true
}
```

`preferred_categories` takes an array of category **slugs**. `preferred_languages` and `preferred_age_groups` take the enum values from the [Enumerations](#enumerations) section.

**Error (username conflict):**

```json
{ "username": ["A user with this username already exists."] }
```

---

### Change Password

```http
POST /api/auth/password/change/
Authorization: Token <token>
```

**Request:**

```json
{
  "old_password": "oldpassword123",
  "new_password1": "newpassword123",
  "new_password2": "newpassword123"
}
```

**Response `200`:**

```json
{ "detail": "Password changed successfully." }
```

**Errors:**

```json
{ "old_password": ["Your old password was entered incorrectly."] }
{ "new_password2": ["The two password fields did not match."] }
{ "new_password1": ["This password is too short. It must contain at least 8 characters."] }
```

---

### Forgot Password

Two-step flow: request a reset email, then confirm with the token from the link.

#### Step 1 — Request reset email

```http
POST /api/auth/password/reset/
```

**Request:**

```json
{ "email": "user@example.com" }
```

**Response `200`** (always the same, regardless of whether the email exists — intentional):

```json
{ "detail": "If that email is registered, a reset link has been sent." }
```

The email contains a link:

```
{FRONTEND_URL}/reset-password?token=<token>
```

Token expires after **1 hour**.

**Error:**

```json
{ "email": ["This field is required."] }
```

#### Step 2 — Confirm reset

```http
POST /api/auth/password/reset/confirm/
```

Extract `token` from the URL query string and POST it with the new password:

**Request:**

```json
{
  "token": "<token from URL query string>",
  "new_password1": "newpassword123",
  "new_password2": "newpassword123"
}
```

**Response `200`:**

```json
{ "detail": "Password reset complete. You can now log in." }
```

After success, redirect to login. No auth token is returned.

**Errors:**

```json
{ "token": ["This reset link is invalid or has expired."] }
{ "new_password2": ["The two password fields did not match."] }
{ "new_password1": ["This password is too short. It must contain at least 8 characters."] }
```

Notes:

- A token is single-use. Submitting it twice returns the invalid/expired error.
- Parse the token with `new URLSearchParams(window.location.search).get('token')`.

---

## Categories

Categories are backend-owned. Always fetch them — never hardcode.

### Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/categories/` | No | List active categories |
| `POST` | `/api/categories/` | Admin | Create category |
| `PATCH` | `/api/categories/<id>/` | Admin | Update category |
| `DELETE` | `/api/categories/<id>/` | Admin | Deactivate category |

### List Categories

```http
GET /api/categories/
```

Returns a flat array (no pagination). Only `is_active=true` categories are included.

**Response `200`:**

```json
[
  {
    "id": 1,
    "name": "Worship",
    "slug": "worship",
    "icon": "heart",
    "description": "Worship and praise gatherings",
    "events_count": 42,
    "is_active": true,
    "sort_order": 1
  }
]
```

**Field notes:**

- `slug` — use this as the filter value: `GET /api/events/?category=worship`
- `icon` — string key the frontend maps to an icon component
- `events_count` — approved events only
- `sort_order` — controls display order

### Create Category (Admin)

```http
POST /api/categories/
Authorization: Token <admin-token>
```

**Request:**

```json
{
  "name": "Arts",
  "slug": "arts",
  "icon": "camera",
  "description": "Art exhibitions and creative events",
  "sort_order": 11,
  "is_active": true
}
```

`slug` auto-generates from `name` if omitted. `icon` defaults to `"zap"`. `is_active` defaults to `true`.

**Response `201`:** Full category object.

### Update Category (Admin)

```http
PATCH /api/categories/<id>/
Authorization: Token <admin-token>
```

Accepts any subset of: `name`, `slug`, `icon`, `description`, `sort_order`, `is_active`.

**Response `200`:** Full updated category object.

### Deactivate Category (Admin)

```http
DELETE /api/categories/<id>/
Authorization: Token <admin-token>
```

Soft-delete — sets `is_active=false`. The category is hidden from public but events are not deleted.

**Response `200`:** Category object with `is_active: false`.

---

## Events

### Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/events/` | No (auth-aware) | Paginated approved event list |
| `POST` | `/api/events/` | Yes | Create event |
| `GET` | `/api/events/<id>/` | No (auth-aware) | Event detail |
| `PATCH` | `/api/events/<id>/` | Owner or admin | Update event |
| `DELETE` | `/api/events/<id>/` | Owner or admin | Delete event |
| `GET` | `/api/events/<id>/related/` | No (auth-aware) | Up to 6 related events |
| `POST` | `/api/events/<id>/like/` | Yes | Toggle like |
| `POST` | `/api/events/<id>/save/` | Yes | Toggle save |
| `POST` | `/api/events/<id>/rsvp/` | Yes | Toggle RSVP |
| `GET` | `/api/events/<id>/attendees/` | Owner or admin | Attendee list |
| `GET` | `/api/events/liked/` | Yes | Current user's liked events |
| `GET` | `/api/events/saved/` | Yes | Current user's saved events |
| `GET` | `/api/events/my-events/` | Yes | Events created by current user |
| `GET` | `/api/events/attending/` | Yes | Events user has RSVPed to |

`PUT` is not supported. Use `PATCH` for updates.

### Event Object

```json
{
  "id": 12,
  "title": "Sunday Night Worship",
  "description": "A night of praise and worship.",
  "organizer": "Lagos Christian Center",
  "date": "2026-12-01T09:00:00Z",
  "end_date": "2026-12-01T12:00:00Z",
  "location": "Faith Tabernacle, Lagos",
  "location_lat": 6.5244,
  "location_lng": 3.3792,
  "pricing": "free",
  "ticket_price": null,
  "category": {
    "id": 1,
    "name": "Worship",
    "slug": "worship",
    "icon": "heart"
  },
  "language": "english",
  "age_group": "all_ages",
  "capacity": 500,
  "rsvp_count": 87,
  "is_rsvped": false,
  "is_full": false,
  "is_featured": false,
  "approval_status": "approved",
  "rejection_reason": null,
  "image": "http://localhost:8000/media/events/cover.jpg",
  "created_by": {
    "id": 1,
    "first_name": "Desmond",
    "last_name": "Egya"
  },
  "is_liked": false,
  "is_saved": false,
  "likes_count": 45,
  "saves_count": 23,
  "created_at": "2026-11-01T12:00:00Z",
  "updated_at": "2026-11-05T08:30:00Z"
}
```

**Auth-aware fields** — `is_liked`, `is_saved`, `is_rsvped` are always present. They are `false` for unauthenticated requests, not omitted.

**`rejection_reason`** — `null` unless the event was rejected by an admin and a reason was provided.

**`image`** — absolute URL or `null` if no image was uploaded.

---

### List Events

```http
GET /api/events/
```

Returns approved events only. Supports filtering, searching, and ordering.

**Query parameters:**

| Param | Example | Notes |
|---|---|---|
| `search` | `?search=shiloh` | Matches `title`, `description`, `location` (case-insensitive) |
| `category` | `?category=worship` | Filter by category slug |
| `pricing` | `?pricing=free` | `free` or `paid` |
| `language` | `?language=english` | Exact enum value |
| `age_group` | `?age_group=young_adults` | Exact enum value |
| `is_featured` | `?is_featured=true` | `true` or `false` |
| `ordering` | `?ordering=-date` | `date`, `created_at`, `title` — prefix `-` for descending |
| `page` | `?page=2` | Default `1` |
| `page_size` | `?page_size=24` | Default `12`, max `50` |

Default ordering is `date` ascending (soonest first).

**Response `200`:** Paginated event list.

---

### Create Event

```http
POST /api/events/
Authorization: Token <token>
```

Accepts `application/json` or `multipart/form-data` (when uploading an image).

**Request:**

```json
{
  "title": "Sunday Night Worship",
  "description": "A night of praise and worship.",
  "organizer": "Lagos Christian Center",
  "date": "2026-12-01T09:00:00Z",
  "end_date": "2026-12-01T12:00:00Z",
  "location": "Faith Tabernacle, Lagos",
  "location_lat": 6.5244,
  "location_lng": 3.3792,
  "pricing": "free",
  "ticket_price": null,
  "category": "worship",
  "language": "english",
  "age_group": "all_ages",
  "capacity": 500
}
```

**Required fields:** `title`, `description`, `date`, `location`, `pricing`, `category`, `language`, `age_group`

**Optional fields:** `organizer`, `end_date`, `location_lat`, `location_lng`, `ticket_price`, `capacity`, `image`

**Validation rules:**

- `category` must be an active category slug
- `end_date` must be after `date`
- `ticket_price` is required when `pricing` is `paid`
- `ticket_price` is forced to `null` when `pricing` is `free`
- `capacity` must be a non-negative integer

**Response `201`:** The created event object.

New events are created with `approval_status: "pending"` and are not visible in the public list until an admin approves them.

---

### Get Event

```http
GET /api/events/<id>/
```

No auth required. Returns auth-aware fields when a valid token is provided.

Owners and admins can also see their own pending/rejected events via this endpoint.

**Response `200`:** Event object.

**Error:**

```json
{ "detail": "Not found." }
```

---

### Update Event

```http
PATCH /api/events/<id>/
Authorization: Token <token>
```

Owner or admin only. Accepts any subset of create fields.

**Additional fields for admins only:**

```json
{
  "approval_status": "approved",
  "rejection_reason": "Incomplete event details.",
  "is_featured": true
}
```

Changing `approval_status` triggers a notification to the event creator:

- `approved` → `event_approved` notification
- `rejected` → `event_rejected` notification (with `rejection_reason` as the detail)

**Response `200`:** Updated event object.

---

### Delete Event

```http
DELETE /api/events/<id>/
Authorization: Token <token>
```

Owner or admin only.

If the event was approved, all users who RSVPed receive an `event_cancelled` notification.

**Response `200`:**

```json
{ "detail": "Event deleted successfully." }
```

---

### Related Events

```http
GET /api/events/<id>/related/
```

Returns up to 6 approved events in the same category, excluding the current event, ordered by `date` ascending.

**Response `200`:**

```json
{
  "count": 4,
  "results": [ "...Event objects..." ]
}
```

---

### Personal Collections

These return flat `Event[]` arrays (no pagination wrapper).

```http
GET /api/events/liked/
GET /api/events/saved/
GET /api/events/attending/
GET /api/events/my-events/
Authorization: Token <token>
```

- `liked`, `saved`, `attending` — approved events only
- `my-events` — all statuses; use this for organizer dashboards so creators can see pending and rejected events

---

## Likes & Saves

Both are toggle endpoints. One call to activate, another to deactivate.

### Toggle Like

```http
POST /api/events/<id>/like/
Authorization: Token <token>
```

**Response when liked:**

```json
{ "liked": true, "likes_count": 46, "message": "Event liked" }
```

**Response when unliked:**

```json
{ "liked": false, "likes_count": 45, "message": "Event unliked" }
```

### Toggle Save

```http
POST /api/events/<id>/save/
Authorization: Token <token>
```

**Response when saved:**

```json
{ "saved": true, "saves_count": 24, "message": "Event saved" }
```

**Response when unsaved:**

```json
{ "saved": false, "saves_count": 23, "message": "Event unsaved" }
```

---

## RSVP & Attendance

### Toggle RSVP

```http
POST /api/events/<id>/rsvp/
Authorization: Token <token>
```

**Response when RSVPed:**

```json
{
  "rsvped": true,
  "rsvp_count": 87,
  "message": "You're going! We'll remind you before the event."
}
```

Creating an RSVP also creates an `rsvp_confirmed` notification for the user.

**Response when cancelled:**

```json
{
  "rsvped": false,
  "rsvp_count": 86,
  "message": "You're no longer going."
}
```

**Error when event is full:**

```json
{ "detail": "This event is at full capacity." }
```

Status `400`. Use `event.is_full` from the event object to disable the RSVP button before this call.

---

### Attendee List

```http
GET /api/events/<id>/attendees/
Authorization: Token <token>
```

Owner or admin only.

**Response `200`:**

```json
{
  "count": 87,
  "results": [
    {
      "id": 1,
      "first_name": "Ada",
      "last_name": "Obi",
      "email": "ada@example.com",
      "rsvped_at": "2026-11-20T10:00:00Z"
    }
  ]
}
```

---

## Notifications

### Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/notifications/` | Yes | Paginated notifications |
| `POST` | `/api/notifications/<id>/read/` | Yes | Mark one as read |
| `POST` | `/api/notifications/read-all/` | Yes | Mark all as read |
| `GET` | `/api/notifications/unread-count/` | Yes | Unread count for navbar badge |
| `DELETE` | `/api/notifications/<id>/` | Yes | Delete notification |

### Notification Object

```json
{
  "id": 1,
  "type": "rsvp_confirmed",
  "title": "You're going!",
  "body": "Your RSVP for Sunday Night Worship is confirmed.",
  "detail": "",
  "event": {
    "id": 12,
    "title": "Sunday Night Worship",
    "image": "http://localhost:8000/media/events/cover.jpg"
  },
  "is_read": false,
  "created_at": "2026-11-20T10:00:00Z"
}
```

`event` is `null` when the notification is not linked to an event. `detail` is an empty string when not set.

### List Notifications

```http
GET /api/notifications/
Authorization: Token <token>
```

**Query params:**

| Param | Example | Notes |
|---|---|---|
| `page` | `?page=2` | |
| `page_size` | `?page_size=20` | Default 12, max 50 |
| `is_read` | `?is_read=false` | Filter by read state |

**Response `200`:** Paginated notification list.

### Mark One Read

```http
POST /api/notifications/<id>/read/
Authorization: Token <token>
```

**Response `200`:** The updated notification object with `is_read: true`.

### Mark All Read

```http
POST /api/notifications/read-all/
Authorization: Token <token>
```

**Response `200`:**

```json
{ "updated": 3 }
```

### Unread Count

```http
GET /api/notifications/unread-count/
Authorization: Token <token>
```

**Response `200`:**

```json
{ "count": 3 }
```

Poll this on app load to populate the navbar badge.

### Delete Notification

```http
DELETE /api/notifications/<id>/
Authorization: Token <token>
```

**Response `204` No Content.**

### Notification types

| `type` | When it fires |
|---|---|
| `event_approved` | Admin approves an organizer's event |
| `event_rejected` | Admin rejects an event (detail contains rejection reason) |
| `rsvp_confirmed` | User RSVPs to an event |
| `event_cancelled` | An approved event is deleted; sent to all RSVPed users |
| `reminder` | 24h before a saved or RSVPed event (requires background worker) |
| `new_event_nearby` | New approved event matches user's preferred categories (requires background worker) |

---

## Public Users

### Public Profile

```http
GET /api/users/<id>/
```

No auth required.

**Response `200`:**

```json
{
  "id": 1,
  "first_name": "Desmond",
  "last_name": "Egya",
  "events_created_count": 12,
  "date_joined": "2026-01-15T12:00:00Z"
}
```

`events_created_count` counts approved events only.

### Public User Events

```http
GET /api/users/<id>/events/
```

No auth required (auth-aware). Returns a paginated list of that user's approved events. Supports `page` and `page_size`.

---

## Images

Event images are optional. Submit as `multipart/form-data` with field name `image`.

**Accepted types:** `image/jpeg`, `image/png`, `image/webp`

**Rules:**

- Max size: **10 MB** — enforced on the backend
- Images wider than **1200px** are resized on upload (aspect ratio preserved)
- The `image` field in all event responses is an absolute URL, e.g. `http://localhost:8000/media/events/cover.jpg`
- When no image is set, `image` is `null`

**Do not set `Content-Type: application/json`** when uploading an image. Let the browser set the `multipart/form-data` boundary automatically.

**Validation errors:**

```json
{ "image": ["Image must not exceed 10 MB."] }
{ "image": ["Upload a JPEG, PNG, or WEBP image."] }
{ "image": ["Upload a valid image file."] }
```

---

## Enumerations

These are the exact values the API accepts and returns.

### `pricing`

| Value | Display |
|---|---|
| `free` | Free |
| `paid` | Paid |

### `language`

| Value | Display |
|---|---|
| `english` | English |
| `yoruba` | Yoruba |
| `igbo` | Igbo |
| `hausa` | Hausa |
| `pidgin` | Pidgin |
| `french` | French |
| `multilingual` | Multilingual |

### `age_group`

| Value | Display |
|---|---|
| `all_ages` | All Ages |
| `children` | Children (0–12) |
| `teenagers` | Teenagers (13–19) |
| `young_adults` | Young Adults (20–35) |
| `adults` | Adults (36–60) |
| `seniors` | Seniors (60+) |

### `approval_status`

| Value | Meaning |
|---|---|
| `pending` | Awaiting admin review — not visible in public event list |
| `approved` | Live — visible to everyone |
| `rejected` | Rejected by admin — visible only to creator and admins |

### `notification_type`

| Value |
|---|
| `reminder` |
| `event_approved` |
| `event_rejected` |
| `new_event_nearby` |
| `rsvp_confirmed` |
| `event_cancelled` |

---

## Error Reference

| Status | Meaning |
|---|---|
| `400` | Bad request — validation error or invalid JSON |
| `401` | Missing or invalid token |
| `403` | Authenticated but not permitted |
| `404` | Resource not found |
| `405` | Method not allowed |
| `500` | Unexpected server error |

All error responses are JSON. `404` on any unknown `/api/*` route returns:

```json
{ "detail": "Not found." }
```

`500` returns:

```json
{ "detail": "An unexpected error occurred." }
```
