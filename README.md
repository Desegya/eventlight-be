# EventLight Backend

Django backend for the EventLight frontend.

The API is designed to run locally at:

```text
http://localhost:8000/api
```

It currently uses plain Django, SQLite, and a small custom token-auth layer. The frontend should send authenticated requests with:

```http
Authorization: Token <token>
```

## Requirements

- Python 3.14
- Pipenv
- Django

Install dependencies:

```bash
pipenv install
```

Enter the virtual environment:

```bash
pipenv shell
```

Or run commands through Pipenv without activating the shell:

```bash
pipenv run python manage.py check
```

## Setup

Apply database migrations:

```bash
pipenv run python manage.py migrate
```

Create an admin user, if needed:

```bash
pipenv run python manage.py createsuperuser
```

Run the development server:

```bash
pipenv run python manage.py runserver 0.0.0.0:8000
```

The frontend can then call:

```text
http://localhost:8000/api
```

## Tests

Run the test suite:

```bash
pipenv run python manage.py test
```

Run Django system checks:

```bash
pipenv run python manage.py check
```

## API Overview

### Auth

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `POST` | `/api/auth/register/` | No | Register user and return token |
| `POST` | `/api/auth/login/` | No | Login and return token |
| `POST` | `/api/auth/logout/` | Yes | Delete current token |
| `GET` | `/api/auth/user/` | Yes | Get current user profile |
| `PATCH` | `/api/auth/user/` | Yes | Update current user profile |
| `POST` | `/api/auth/password/change/` | Yes | Change password |
| `POST` | `/api/auth/password/reset/` | No | Password reset placeholder |
| `POST` | `/api/auth/password/reset/confirm/` | No | Password reset confirm placeholder |

### Categories

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/api/categories/` | No | List active admin-managed event categories |

### Events

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/api/events/` | No | List events as a plain JSON array |
| `POST` | `/api/events/` | Yes | Create event with JSON or multipart data |
| `GET` | `/api/events/<id>/` | No | Get event detail |
| `PUT` | `/api/events/<id>/` | Yes | Partially update event with JSON or multipart data |
| `DELETE` | `/api/events/<id>/` | Yes | Delete event and return JSON |
| `POST` | `/api/events/<id>/like/` | Yes | Toggle like |
| `POST` | `/api/events/<id>/save/` | Yes | Toggle save |
| `GET` | `/api/events/liked/` | Yes | List current user's liked events |
| `GET` | `/api/events/saved/` | Yes | List current user's saved events |
| `GET` | `/api/events/my-events/` | Yes | List current user's created events |

## User Shape

Current user responses include:

```json
{
  "id": 1,
  "email": "user@example.com",
  "first_name": "John",
  "last_name": "Doe",
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
  "event_reminders": true
}
```

## Event Shape

Event responses include:

```json
{
  "id": 1,
  "title": "Sunday Worship Service",
  "description": "Join us for worship.",
  "organizer": "Lagos Christian Center",
  "date": "2026-06-01T10:00:00Z",
  "location": "Lagos Christian Center",
  "pricing": "free",
  "category": "worship",
  "event_type": "church_service",
  "language": "english",
  "age_group": "all_ages",
  "created_by": 1,
  "approval_status": "approved",
  "image": null,
  "created_at": "2026-05-09T12:00:00Z",
  "is_liked": false,
  "is_saved": false,
  "likes_count": 0,
  "saves_count": 0
}
```

## CORS And Media

Development CORS allows:

```text
http://localhost:5173
```

Uploaded event media is stored under `media/` and served by Django while `DEBUG = True`.

## Notes

- Event list endpoints return plain arrays, not paginated objects.
- Event categories are managed in Django admin and exposed as slugs in event API responses.
- `created_by` is the user account that created the record; `organizer` is the public organizer name typed for the event.
- Logout and delete endpoints return JSON because the frontend calls `response.json()`.
- Password reset endpoints currently return compatibility responses only; email delivery is not implemented.
- The SQLite database is local development storage.
