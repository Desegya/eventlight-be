# EventLight Backend

Backend API for the EventLight frontend.

Full endpoint reference: [API.md](API.md). Deployment: [Production Deployment](#production-deployment). The development API base URL is:

```text
http://localhost:8000/api
```

The Vite frontend runs at:

```text
http://localhost:5173
```

## Stack

- Python 3.14, Django 6, gunicorn, WhiteNoise
- SQLite locally, Postgres in production (`DATABASE_URL`)
- django-rest-knox tokens delivered as an httpOnly `auth_token` cookie (CSRF-protected); `Authorization: Token <token>` also accepted
- Pillow image processing, optional Cloudinary media storage
- ZeptoMail REST API for email, optional Sentry

## Local Setup

Install dependencies (exact versions from `Pipfile.lock`):

```bash
pipenv sync
cp .env.example .env   # then set DEBUG=true for local development
```

Apply migrations:

```bash
pipenv run python manage.py migrate
```

Create an admin user:

```bash
pipenv run python manage.py createsuperuser
```

Run the backend:

```bash
pipenv run python manage.py runserver 0.0.0.0:8000
```

Run checks and tests (tests never send email, even with a real key in `.env`):

```bash
pipenv run python manage.py check
pipenv run python manage.py makemigrations --check --dry-run
pipenv run python manage.py test
```

Seed local demo data:

```bash
pipenv run python manage.py seed_demo_data --clear
```

This creates demo categories, users, approved/pending/rejected events, RSVPs, likes, saves, and notifications. Demo users use `password123` and emails ending in `@eventlight.test`. The command refuses to run with `DEBUG=false` (pass `--allow-production` to override deliberately).

## Frontend Defaults

Set the frontend API URL to:

```env
VITE_API_URL=http://localhost:8000/api
```

Authenticated requests must include:

```http
Authorization: Token <token>
```

Use `Content-Type: application/json` for JSON requests. Do not set `Content-Type` manually for `multipart/form-data`; let the browser set the boundary.

## Response Conventions

All timestamps are ISO 8601 UTC strings:

```text
2026-12-01T09:00:00Z
```

General errors:

```json
{
  "detail": "Authentication credentials were not provided."
}
```

Validation errors:

```json
{
  "title": ["This field is required."]
}
```

Unknown `/api/*` routes return JSON:

```json
{
  "detail": "Not found."
}
```

Paginated responses use:

```json
{
  "count": 143,
  "next": "http://localhost:8000/api/events/?page=2",
  "previous": null,
  "results": []
}
```

Pagination defaults:

- `page_size=12`
- max `page_size=50`

## Auth

### Endpoints

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/auth/register/` | No | Register and return token plus user |
| `POST` | `/api/auth/login/` | No | Login and return token plus user |
| `POST` | `/api/auth/logout/` | Yes | Invalidate current token |
| `GET` | `/api/auth/user/` | Yes | Current user profile |
| `PATCH` | `/api/auth/user/` | Yes | Update profile |
| `POST` | `/api/auth/password/change/` | Yes | Change password |
| `POST` | `/api/auth/password/reset/` | No | Compatibility response |
| `POST` | `/api/auth/password/reset/confirm/` | No | Compatibility response |

### Register

```http
POST /api/auth/register/
```

Request:

```json
{
  "email": "user@example.com",
  "password": "<password>",
  "first_name": "Desmond",
  "last_name": "Egya",
  "username": "desmond_e"
}
```

Response `201`:

```json
{
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

### Login

```http
POST /api/auth/login/
```

Request:

```json
{
  "email": "user@example.com",
  "password": "<password>"
}
```

Response `200`:

```json
{
  "user": { "...": "full user object" }
}
```

### Current User

```http
GET /api/auth/user/
PATCH /api/auth/user/
```

`PATCH` accepts any subset of:

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

Response is always the full user object.

### Change Password

```http
POST /api/auth/password/change/
```

Request:

```json
{
  "old_password": "<current password>",
  "new_password1": "<new password>",
  "new_password2": "<new password>"
}
```

Response:

```json
{
  "detail": "Password changed successfully."
}
```

Password reset email delivery is not implemented yet. The reset endpoints currently return compatibility JSON responses.

## Categories

Categories are backend-owned. The frontend should fetch them instead of hardcoding category options.

### Endpoints

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/categories/` | No | List active categories |
| `POST` | `/api/categories/` | Admin token | Create category |
| `PATCH` | `/api/categories/<id>/` | Admin token | Update category |
| `DELETE` | `/api/categories/<id>/` | Admin token | Deactivate category |

### Category Object

```json
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
```

Field notes:

- `slug` is what the frontend sends to `GET /api/events/?category=worship`.
- `icon` is a key the frontend maps to an icon component.
- `events_count` counts approved events only.
- Public `GET /api/categories/` returns active categories only.
- `DELETE /api/categories/<id>/` deactivates the category; it does not hard-delete.

Seeded categories:

| Name | Slug | Icon |
| --- | --- | --- |
| Worship | `worship` | `heart` |
| Music | `music` | `music` |
| Conference | `conference` | `mic` |
| Seminar | `seminar` | `book` |
| Fellowship | `fellowship` | `users` |
| Prayer | `prayer` | `sun` |
| Youth | `youth` | `award` |
| Outreach | `outreach` | `message` |
| Teaching | `teaching` | `book` |
| Children | `children` | `star` |

## Events

### Endpoints

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/events/` | No, auth-aware | Paginated approved event list |
| `POST` | `/api/events/` | Yes | Create pending event |
| `GET` | `/api/events/<id>/` | No, auth-aware | Event detail |
| `PATCH` | `/api/events/<id>/` | Owner or admin | Update event |
| `DELETE` | `/api/events/<id>/` | Owner or admin | Delete event |
| `GET` | `/api/events/<id>/related/` | No, auth-aware | Up to 6 related events |
| `POST` | `/api/events/<id>/like/` | Yes | Toggle like |
| `POST` | `/api/events/<id>/save/` | Yes | Toggle save |
| `POST` | `/api/events/<id>/rsvp/` | Yes | Toggle RSVP |
| `GET` | `/api/events/<id>/attendees/` | Owner or admin | RSVP attendee list |
| `GET` | `/api/events/liked/` | Yes | Current user's liked events |
| `GET` | `/api/events/saved/` | Yes | Current user's saved events |
| `GET` | `/api/events/my-events/` | Yes | Current user's events, all statuses |
| `GET` | `/api/events/attending/` | Yes | Current user's RSVPed events |

`PUT` is intentionally not supported. Use `PATCH` for updates.

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

Auth-aware fields:

- `is_liked`
- `is_saved`
- `is_rsvped`

For unauthenticated requests, these are returned as `false`, not omitted.

### List Events

```http
GET /api/events/
```

Returns approved events only.

Supported query params:

| Param | Example | Notes |
| --- | --- | --- |
| `search` | `?search=shiloh` | Matches `title`, `description`, `location` |
| `category` | `?category=worship` | Matches category slug |
| `pricing` | `?pricing=free` | `free` or `paid` |
| `language` | `?language=english` | Exact enum value |
| `age_group` | `?age_group=young_adults` | Exact enum value |
| `is_featured` | `?is_featured=true` | Boolean filter |
| `ordering` | `?ordering=-date` | Supports `date`, `created_at`, `title` |
| `page` | `?page=2` | Page number |
| `page_size` | `?page_size=12` | Default 12, max 50 |

Example:

```http
GET /api/events/?search=worship&category=worship&language=english&page=1&page_size=12
```

Response:

```json
{
  "count": 143,
  "next": "http://localhost:8000/api/events/?page=2",
  "previous": null,
  "results": [
    { "...": "Event object" }
  ]
}
```

### Create Event

```http
POST /api/events/
```

Requires auth. Created events start as:

```json
{
  "approval_status": "pending"
}
```

They do not appear in the public event list until an admin approves them.

JSON request:

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

Required fields:

- `title`
- `description`
- `date`
- `location`
- `pricing`
- `category`
- `language`
- `age_group`

Optional fields:

- `organizer`
- `end_date`
- `location_lat`
- `location_lng`
- `ticket_price`
- `capacity`
- `image`

Validation:

- `category` must be an active category slug.
- `end_date` must be after `date`.
- `ticket_price` is required when `pricing` is `paid`.
- `ticket_price` is forced to `null` when `pricing` is `free`.
- `capacity` must be a non-negative integer when provided.

Multipart request fields use the same names. Include `image=<file>` when uploading.

### Update Event

```http
PATCH /api/events/<id>/
```

Owner or admin only. Accepts any subset of create fields. Admin users may also update:

```json
{
  "approval_status": "approved",
  "rejection_reason": "",
  "is_featured": true
}
```

Approval or rejection updates create a notification for the event creator.

### Delete Event

```http
DELETE /api/events/<id>/
```

Owner or admin only.

Response:

```json
{
  "detail": "Event deleted successfully."
}
```

If the event was approved, RSVPed users receive an `event_cancelled` notification.

### Related Events

```http
GET /api/events/<id>/related/
```

Returns up to 6 approved events in the same category, excluding the current event.

Response:

```json
{
  "count": 4,
  "results": [
    { "...": "Event object" }
  ]
}
```

### Personal Event Collections

These return flat arrays, not paginated objects:

```http
GET /api/events/liked/
GET /api/events/saved/
GET /api/events/my-events/
GET /api/events/attending/
```

Notes:

- `liked`, `saved`, and `attending` return approved events only.
- `my-events` returns all statuses so creators can see pending and rejected events.

## Likes And Saves

### Like

```http
POST /api/events/<id>/like/
```

Response when liked:

```json
{
  "liked": true,
  "likes_count": 46,
  "message": "Event liked"
}
```

Response when unliked:

```json
{
  "liked": false,
  "likes_count": 45,
  "message": "Event unliked"
}
```

### Save

```http
POST /api/events/<id>/save/
```

Response when saved:

```json
{
  "saved": true,
  "saves_count": 24,
  "message": "Event saved"
}
```

Response when unsaved:

```json
{
  "saved": false,
  "saves_count": 23,
  "message": "Event unsaved"
}
```

## RSVP And Attendance

### Toggle RSVP

```http
POST /api/events/<id>/rsvp/
```

Response when RSVP is created:

```json
{
  "rsvped": true,
  "rsvp_count": 87,
  "message": "You're going! We'll remind you before the event."
}
```

Response when RSVP is cancelled:

```json
{
  "rsvped": false,
  "rsvp_count": 86,
  "message": "You're no longer going."
}
```

If the event is full:

```json
{
  "detail": "This event is at full capacity."
}
```

RSVP creates an `rsvp_confirmed` notification for the current user.

### Attendees

```http
GET /api/events/<id>/attendees/
```

Owner or admin only.

Response:

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

## Notifications

### Endpoints

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/notifications/` | Yes | Paginated notifications |
| `POST` | `/api/notifications/<id>/read/` | Yes | Mark one notification read |
| `POST` | `/api/notifications/read-all/` | Yes | Mark all notifications read |
| `GET` | `/api/notifications/unread-count/` | Yes | Navbar unread badge |
| `DELETE` | `/api/notifications/<id>/` | Yes | Delete notification |

### Notification Object

```json
{
  "id": 1,
  "type": "reminder",
  "title": "Event starts tomorrow",
  "body": "Shiloh 2026 is tomorrow. Don't miss it!",
  "detail": "You saved this event. It starts tomorrow at 9 AM.",
  "event": {
    "id": 12,
    "title": "Shiloh 2026",
    "image": "http://localhost:8000/media/events/cover.jpg"
  },
  "is_read": false,
  "created_at": "2026-11-30T08:00:00Z"
}
```

`GET /api/notifications/` supports:

| Param | Example |
| --- | --- |
| `page` | `?page=2` |
| `page_size` | `?page_size=12` |
| `is_read` | `?is_read=false` |

Unread count:

```http
GET /api/notifications/unread-count/
```

```json
{
  "count": 3
}
```

Mark all read:

```http
POST /api/notifications/read-all/
```

```json
{
  "updated": 3
}
```

Delete:

```http
DELETE /api/notifications/<id>/
```

Returns `204 No Content`.

Implemented notification types:

| Type | Created when |
| --- | --- |
| `event_approved` | Admin approves an event |
| `event_rejected` | Admin rejects an event |
| `rsvp_confirmed` | User RSVPs to an event |
| `event_cancelled` | Approved event is deleted and users had RSVPed |

The `reminder` and `new_event_nearby` types exist in the model but need a background worker or explicit trigger before they are generated automatically.

## Public Users

### Public Profile

```http
GET /api/users/<id>/
```

Response:

```json
{
  "id": 1,
  "first_name": "Desmond",
  "last_name": "Egya",
  "events_created_count": 12,
  "date_joined": "2026-01-15T12:00:00Z"
}
```

### Public User Events

```http
GET /api/users/<id>/events/
```

Returns a paginated list of that user's approved events. Response shape is the standard paginated event response.

## Images

Event images are optional.

Accepted MIME types:

- `image/jpeg`
- `image/png`
- `image/webp`

Rules:

- Max size is 10 MB.
- Images wider than 1200px are resized on upload.
- Image URLs in event responses are absolute.

Validation errors:

```json
{
  "image": ["Image must not exceed 10 MB."]
}
```

## Enumerations

### Pricing

| Value | Display |
| --- | --- |
| `free` | Free |
| `paid` | Paid |

### Language

| Value | Display |
| --- | --- |
| `english` | English |
| `yoruba` | Yoruba |
| `igbo` | Igbo |
| `hausa` | Hausa |
| `pidgin` | Pidgin |
| `french` | French |
| `multilingual` | Multilingual |

### Age Group

| Value | Display |
| --- | --- |
| `all_ages` | All Ages |
| `children` | Children (0-12) |
| `teenagers` | Teenagers (13-19) |
| `young_adults` | Young Adults (20-35) |
| `adults` | Adults (36-60) |
| `seniors` | Seniors (60+) |

### Approval Status

| Value | Meaning |
| --- | --- |
| `pending` | Awaiting admin review |
| `approved` | Publicly visible |
| `rejected` | Rejected by admin |

### Notification Type

| Value |
| --- |
| `reminder` |
| `event_approved` |
| `event_rejected` |
| `new_event_nearby` |
| `rsvp_confirmed` |
| `event_cancelled` |

## CORS and CSRF

Browsers call the API with `credentials: "include"`. Set both lists to the
deployed frontend origin(s):

- `CORS_ALLOWED_ORIGINS`: origins allowed to call the API with credentials.
- `CSRF_TRUSTED_ORIGINS`: origins allowed to send POST/PATCH/DELETE.

Allowed request headers: `authorization`, `content-type`, `x-csrftoken`,
`x-request-id`. Exposed response header: `x-request-id`. See
[API.md › CSRF](API.md#csrf) for the token flow.

## Admin Behavior

The Django admin is configured for operations:

- Event forms are grouped into basics, schedule, location, pricing/capacity, audience, review, ownership, and engagement sections.
- Admin-created events automatically set `created_by` to the logged-in admin.
- Event lists support bulk approve, reject, pending, feature, and unfeature actions.
- Approval and rejection create organizer notifications.
- Deleting approved events creates cancellation notifications for RSVPed users.
- Event detail pages show image preview, RSVP count, full state, likes, saves, and inline RSVP/like/save rows.
- Categories show icon, sort order, active state, approved event count, and total event count.
- Notifications support bulk mark read/unread.
- Users show created, liked, saved, attending, and unread notification counts.

## Frontend Integration Checklist

- Send every request with `credentials: "include"`; never store tokens in JS.
- Before POST/PATCH/DELETE, get a token from `GET /api/auth/csrf/` (use the `csrfToken` body field when the API is on another site) and send it as `X-CSRFToken`; on `403` with `"code": "csrf_failed"`, refetch and retry once.
- Treat `401` from any endpoint as "signed out".
- Read categories from `GET /api/categories/`; use `category.slug` as the filter value.
- Read event lists from `response.results`; pass `upcoming=true` for discovery views.
- Use `is_liked`, `is_saved`, `is_rsvped`, `rsvp_count` and `is_full` from event responses.
- Use `GET /api/events/my-events/` for organizer dashboards (includes pending/rejected events with `rejection_reason`).
- Use `PATCH`, not `PUT`, for event updates. Owner edits to approved events send them back to review.

## Production Deployment

The API and the frontend are separate deployments. Before the first launch:

1. **Environment** (see `.env.example`): `DEBUG=false`, a strong `SECRET_KEY`,
   `ALLOWED_HOSTS`, `DATABASE_URL` (Postgres), `CORS_ALLOWED_ORIGINS` and
   `CSRF_TRUSTED_ORIGINS` (frontend origin), `FRONTEND_URL`, `CLOUDINARY_URL`,
   `ZEPTOMAIL_API_KEY`, and `NUM_TRUSTED_PROXIES` (1 behind a single platform
   proxy such as Railway/Render/Heroku; it decides which `X-Forwarded-For`
   entry rate limiting trusts).
2. **Same-site hosting.** Auth uses cookies. If the API is on a different
   *site* from the frontend (e.g. `*.vercel.app` and `*.up.railway.app`),
   browsers that block third-party cookies (Safari by default, and any user
   who enables the setting) will not keep users signed in. Serve both from one
   registrable domain (`app.example.com` + `api.example.com`) or have the
   frontend host proxy `/api` to this service.
3. **Release step** (Procfile `release`, Docker `CMD`): `migrate` and
   `createcachetable` (the database cache holds rate-limit counters shared by
   all workers).
4. **Verify config:** `python manage.py check --deploy` warns (`eventlight.W00x`)
   about localhost URLs, CORS origins missing from `CSRF_TRUSTED_ORIGINS`,
   missing Cloudinary or email settings.
5. **Scheduled job:** run `python manage.py send_event_reminders` hourly
   (Railway/Render cron) so RSVP/saved-event reminders are delivered.
6. **Probes:** liveness `GET /api/health/`, readiness `GET /api/health/ready/`.
7. **Operations:** logs include a request ID (`X-Request-ID`) per line; set
   `SENTRY_DSN` to capture errors. Take regular Postgres backups (managed
   provider snapshots or `pg_dump`) and test a restore before launch.
   Migrations run automatically on release; before a destructive migration,
   take a backup and plan a rollback.

Rotate `SECRET_KEY` and the ZeptoMail key if they have ever been shared or
committed. The insecure fallback key in `config/settings.py` is used only when
`DEBUG=true`.

## Known Gaps

- `new_event_nearby` notifications exist as a type but nothing generates them yet.
- There is no edit-event page in the frontend; the API supports `PATCH`.
- Email is sent from an in-process thread pool; emails queued in a worker that
  is restarted before delivery are lost. Move to a task queue if volume grows.
