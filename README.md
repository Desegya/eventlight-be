# EventLight Backend

Django backend for the EventLight frontend.

Base API URL in development:

```text
http://localhost:8000/api
```

Auth uses token headers:

```http
Authorization: Token <token>
```

## Stack

- Python 3.14
- Django
- Django REST Framework
- django-filter
- django-cors-headers
- Pillow
- SQLite for local development

## Setup

Install dependencies:

```bash
pipenv install
```

Apply migrations:

```bash
pipenv run python manage.py migrate
```

Create an admin user:

```bash
pipenv run python manage.py createsuperuser
```

Run the server:

```bash
pipenv run python manage.py runserver 0.0.0.0:8000
```

Run checks and tests:

```bash
pipenv run python manage.py check
pipenv run python manage.py test
```

## Admin Workflow

The Django admin is configured for operations work:

- Events are grouped into clear sections for basics, schedule, location, pricing, audience, review, ownership, and engagement.
- `created_by` is filled automatically from the logged-in admin when an admin creates an event.
- Event lists support bulk approve, reject, pending, feature, and unfeature actions.
- Approval/rejection changes create organizer notifications.
- Deleting approved events creates cancellation notifications for RSVPed users.
- Event detail pages show image preview, RSVP count, full state, likes, saves, and inline RSVP/like/save records.
- Categories show active state, sort order, icon key, approved event count, and total event count.
- Notifications can be marked read/unread in bulk.
- Users show created, liked, saved, attending, and unread notification counts.

## Auth

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `POST` | `/api/auth/register/` | No | Register and return `{ key, user }` |
| `POST` | `/api/auth/login/` | No | Login and return `{ key, user }` |
| `POST` | `/api/auth/logout/` | Yes | Invalidate current token |
| `GET` | `/api/auth/user/` | Yes | Current user profile |
| `PATCH` | `/api/auth/user/` | Yes | Update profile |
| `POST` | `/api/auth/password/change/` | Yes | Change password |
| `POST` | `/api/auth/password/reset/` | No | Password reset compatibility response |
| `POST` | `/api/auth/password/reset/confirm/` | No | Password reset confirm compatibility response |

## Categories

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/api/categories/` | No | Active categories |
| `POST` | `/api/categories/` | Admin | Create category |
| `PATCH` | `/api/categories/<id>/` | Admin | Update category |
| `DELETE` | `/api/categories/<id>/` | Admin | Deactivate category |

Category response:

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

## Events

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/api/events/` | No, auth-aware | Paginated approved events |
| `POST` | `/api/events/` | Yes | Create pending event |
| `GET` | `/api/events/<id>/` | No, auth-aware | Event detail |
| `PATCH` | `/api/events/<id>/` | Owner/Admin | Update event |
| `DELETE` | `/api/events/<id>/` | Owner/Admin | Delete event |
| `GET` | `/api/events/<id>/related/` | No | Up to 6 related events |
| `POST` | `/api/events/<id>/like/` | Yes | Toggle like |
| `POST` | `/api/events/<id>/save/` | Yes | Toggle save |
| `POST` | `/api/events/<id>/rsvp/` | Yes | Toggle RSVP |
| `GET` | `/api/events/<id>/attendees/` | Owner/Admin | RSVP attendees |
| `GET` | `/api/events/liked/` | Yes | Current user's liked events |
| `GET` | `/api/events/saved/` | Yes | Current user's saved events |
| `GET` | `/api/events/my-events/` | Yes | Current user's events, all statuses |
| `GET` | `/api/events/attending/` | Yes | Current user's RSVPed events |

`GET /api/events/` supports:

```text
search
category
pricing
language
age_group
is_featured
ordering
page
page_size
```

Paginated response:

```json
{
  "count": 143,
  "next": "http://localhost:8000/api/events/?page=2",
  "previous": null,
  "results": []
}
```

Event response includes nested category and creator objects:

```json
{
  "id": 12,
  "title": "Sunday Night Worship",
  "description": "A night of praise...",
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

## RSVP

`POST /api/events/<id>/rsvp/` toggles attendance.

Response:

```json
{
  "rsvped": true,
  "rsvp_count": 87,
  "message": "You're going! We'll remind you before the event."
}
```

If the event has a capacity and is full:

```json
{
  "detail": "This event is at full capacity."
}
```

## Notifications

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/api/notifications/` | Yes | Paginated notifications |
| `POST` | `/api/notifications/<id>/read/` | Yes | Mark one as read |
| `POST` | `/api/notifications/read-all/` | Yes | Mark all as read |
| `DELETE` | `/api/notifications/<id>/` | Yes | Delete notification, returns `204` |
| `GET` | `/api/notifications/unread-count/` | Yes | Navbar unread count |

Notifications are created for RSVP confirmation, event approval, event rejection, and event cancellation. Scheduled reminders are model-ready but need a background worker before production.

## Users

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/api/users/<id>/` | No | Public organizer profile |
| `GET` | `/api/users/<id>/events/` | No, auth-aware | Paginated approved events by user |

Current user profile includes dashboard counts:

```json
{
  "events_created_count": 3,
  "events_liked_count": 12,
  "events_saved_count": 7,
  "events_attending_count": 4
}
```

## Images

Event uploads accept `image/jpeg`, `image/png`, and `image/webp`.

Rules:

- Max file size: 10 MB
- Images wider than 1200px are resized on upload
- Event responses return absolute image URLs

## CORS

Development origins:

```text
http://localhost:5173
```

Allowed headers include `Authorization` and `Content-Type`.

## Errors

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

API 404s return:

```json
{
  "detail": "Not found."
}
```
