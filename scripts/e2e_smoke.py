"""End-to-end contract smoke test for the EventLight API.

Drives the critical journeys the way the frontend's src/services/http.ts does:
cookie session, the SPA's Origin, and the CSRF token taken from the
/auth/csrf/ response body (the cross-site deployment path).

It CREATES users and events, so run it only against development or staging:

    E2E_ADMIN_EMAIL=... E2E_ADMIN_PASSWORD=... \
    E2E_ORIGIN=http://localhost:5173 python scripts/e2e_smoke.py http://127.0.0.1:8000/api

The admin account must be staff. Exits non-zero if any check fails.
"""
import io
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import requests
from PIL import Image

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8765/api'
ORIGIN = os.environ.get('E2E_ORIGIN', 'http://localhost:5173')
RUN = uuid.uuid4().hex[:8]
ADMIN_EMAIL = os.environ['E2E_ADMIN_EMAIL']
ADMIN_PASSWORD = os.environ['E2E_ADMIN_PASSWORD']
results = []


def check(name, condition, detail=''):
    results.append((name, bool(condition)))
    print(f"{'PASS' if condition else 'FAIL'}  {name}{'  -- ' + str(detail) if not condition and detail else ''}")


class Browser:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers['Origin'] = ORIGIN
        self.csrf = None

    def token(self, force=False):
        if force or not self.csrf:
            self.csrf = self.s.get(f'{BASE}/auth/csrf/').json()['csrfToken']
        return self.csrf

    def call(self, method, path, **kw):
        headers = kw.pop('headers', {})
        if method not in ('GET', 'HEAD', 'OPTIONS'):
            headers['X-CSRFToken'] = self.token()
        return self.s.request(method, f'{BASE}{path}', headers=headers, **kw)


# CORS preflight as the browser would send it
pre = requests.options(f'{BASE}/events/', headers={
    'Origin': ORIGIN, 'Access-Control-Request-Method': 'POST',
    'Access-Control-Request-Headers': 'content-type,x-csrftoken'})
check('CORS preflight allows SPA origin with credentials + X-CSRFToken',
      pre.headers.get('access-control-allow-origin') == ORIGIN
      and pre.headers.get('access-control-allow-credentials') == 'true'
      and 'x-csrftoken' in pre.headers.get('access-control-allow-headers', ''), dict(pre.headers))

anon = Browser()
r = anon.s.post(f'{BASE}/auth/register/', json={'email': f'x-{RUN}@e2e.test', 'password': 'whatever-long-pass-1'})
check('Mutating request without CSRF token -> 403 csrf_failed JSON', r.status_code == 403 and r.json().get('code') == 'csrf_failed', r.text[:120])

user = Browser()
r = user.call('POST', '/auth/register/', json={'email': f'ada-{RUN}@e2e.test', 'password': 'password123', 'first_name': 'Ada'})
check('Register rejects a common password with a field error', r.status_code == 400 and 'password' in r.json(), r.text[:200])
r = user.call('POST', '/auth/register/', json={'email': f'ada-{RUN}@e2e.test', 'password': 'violet-harbour-candle-81', 'first_name': 'Ada', 'last_name': 'L'})
cookie = r.cookies.get('auth_token')
set_cookie = r.headers.get('Set-Cookie', '')
check('Register 201, user in body, no token in body, httpOnly cookie set',
      r.status_code == 201 and 'user' in r.json() and 'key' not in r.json() and cookie and 'HttpOnly' in set_cookie, r.text[:200])
check('X-Request-ID returned and exposed to the SPA', r.headers.get('X-Request-ID') and 'x-request-id' in r.headers.get('access-control-expose-headers', '').lower())
check('Session cookie authenticates /auth/user/', user.call('GET', '/auth/user/').json().get('email') == f'ada-{RUN}@e2e.test')

cats = user.call('GET', '/categories/').json()
check('Categories list returns slugs with events_count', cats and {'slug', 'events_count'} <= set(cats[0]))

start = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0)
img = io.BytesIO(); Image.new('RGB', (1600, 900), 'purple').save(img, 'JPEG'); img.seek(0)
form = {'title': 'E2E Choir Night', 'description': 'Songs', 'date': start.isoformat().replace('+00:00', 'Z'),
        'end_date': (start + timedelta(hours=2)).isoformat().replace('+00:00', 'Z'), 'location': 'Lagos',
        'pricing': 'free', 'category': cats[0]['slug'], 'language': 'english', 'age_group': 'all_ages', 'capacity': '1'}
r = user.call('POST', '/events/', data=form, files={'image': ('cover.jpg', img, 'image/jpeg')})
event = r.json()
check('Create event (multipart + image) -> 201 pending, image URL, UTC date preserved',
      r.status_code == 201 and event['approval_status'] == 'pending' and event['image'] and event['date'] == form['date'], r.text[:300])
eid = event['id']

r = user.call('POST', '/events/', json={**form, 'pricing': 'banana', 'title': 'x' * 300})
check('Invalid event -> 400 with per-field errors', r.status_code == 400 and {'pricing', 'title'} <= set(r.json()), r.text[:200])

check('Pending event hidden from anonymous visitors', anon.call('GET', f'/events/{eid}/').status_code == 404)
check('Pending event visible to its organizer in my-events', any(e['id'] == eid for e in user.call('GET', '/events/my-events/').json()))

admin = Browser()
r = admin.call('POST', '/auth/login/', json={'email': ADMIN_EMAIL, 'password': ADMIN_PASSWORD})
check('Admin login 200', r.status_code == 200, r.text[:120])
r = admin.call('PATCH', f'/events/{eid}/', json={'approval_status': 'approved'})
check('Admin approves event', r.json().get('approval_status') == 'approved', r.text[:200])

listing = anon.call('GET', '/events/?upcoming=true&page_size=50').json()
check('Approved upcoming event appears in public upcoming listing', any(e['id'] == eid for e in listing['results']))

r = user.call('POST', f'/events/{eid}/like/')
check('Like toggles and returns count', r.json() == {'liked': True, 'likes_count': 1, 'message': 'Event liked'}, r.text)
r = user.call('POST', f'/events/{eid}/rsvp/')
check('RSVP succeeds', r.json().get('rsvped') is True, r.text)
other = Browser()
other.call('POST', '/auth/register/', json={'email': f'bo-{RUN}@e2e.test', 'password': 'amber-meadow-kettle-55'})
r = other.call('POST', f'/events/{eid}/rsvp/')
check('Second RSVP blocked at capacity 1', r.status_code == 400 and 'capacity' in r.json()['detail'], r.text)
detail = user.call('GET', f'/events/{eid}/').json()
check('Event detail reflects viewer state', detail['is_liked'] and detail['is_rsvped'] and detail['rsvp_count'] == 1 and detail['is_full'])

png = io.BytesIO(); Image.new('RGB', (300, 200), 'orange').save(png, 'PNG'); png.seek(0)
r = user.call('PATCH', f'/events/{eid}/', data={'title': 'E2E Choir Night (edited)'},
              files={'image': ('c2.png', png, 'image/png')})
body = r.json()
check('Multipart PATCH (frontend image-replace path) applies title and image',
      body.get('title') == 'E2E Choir Night (edited)' and body.get('image') != detail['image'], r.text[:200])
check('Organizer edit of approved event returns it to review', body.get('approval_status') == 'pending', r.text[:200])
admin.call('PATCH', f'/events/{eid}/', json={'approval_status': 'approved'})

notes = user.call('GET', '/notifications/unread-count/').json()
check('Organizer received approval/RSVP notifications', notes['count'] >= 2, notes)

r = admin.call('PATCH', f'/events/{eid}/', json={'title': 'hijack'})
check('Admin may edit any event (staff)', r.status_code == 200)
r = other.call('PATCH', f'/events/{eid}/', json={'title': 'hijack'})
check('Non-owner edit -> 403', r.status_code == 403, r.text)
r = other.call('GET', f'/events/{eid}/attendees/')
check('Non-owner cannot read attendee emails -> 403', r.status_code == 403, r.text)

second = Browser()
second.call('POST', '/auth/login/', json={'email': f'ada-{RUN}@e2e.test', 'password': 'violet-harbour-candle-81'})
r = user.call('POST', '/auth/password/change/', json={'old_password': 'violet-harbour-candle-81',
              'new_password1': 'quartz-lantern-orchid-27', 'new_password2': 'quartz-lantern-orchid-27'})
check('Password change 200', r.status_code == 200, r.text)
check('Current session survives password change', user.call('GET', '/auth/user/').status_code == 200)
check('Other session revoked by password change', second.call('GET', '/auth/user/').status_code == 401)

r = user.call('POST', '/auth/logout/')
check('Logout clears cookie', r.status_code == 200 and 'auth_token=""' in r.headers.get('Set-Cookie', ''), r.headers.get('Set-Cookie'))
check('After logout /auth/user/ -> 401', user.call('GET', '/auth/user/').status_code == 401)

r = anon.call('GET', '/definitely/not/here/')
check('Unknown API route -> JSON 404', r.status_code == 404 and r.json() == {'detail': 'Not found.'})
check('Readiness probe OK', requests.get(f'{BASE}/health/ready/').json() == {'status': 'ok', 'database': 'ok'})

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} journeys passed")
sys.exit(1 if failed else 0)
