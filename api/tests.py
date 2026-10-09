import json
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from knox.models import AuthToken

from .models import PasswordResetToken, User


# The developer's .env may hold a real ZeptoMail key; tests must never send mail.
NO_EMAIL = override_settings(ZEPTOMAIL_API_KEY='')
TEST_PASSWORD = 'quiet-harbour-lantern-42'


class ApiTestCase(TestCase):
    def setUp(self):
        # Rate-limit counters live in the cache and would leak between tests.
        cache.clear()


@NO_EMAIL
class ApiContractTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.admin = User.objects.create_user(
            email='admin@example.com',
            username='admin',
            password=TEST_PASSWORD,
            is_staff=True,
        )
        _, self.admin_token = AuthToken.objects.create(user=self.admin)

    def auth(self, token):
        return {'HTTP_AUTHORIZATION': f'Token {token}'}

    def register(self, email='user@example.com', username='johndoe'):
        response = self.client.post(
            '/api/auth/register/',
            data=json.dumps(
                {
                    'email': email,
                    'password': TEST_PASSWORD,
                    'first_name': 'John',
                    'last_name': 'Doe',
                    'username': username,
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIn('user', body)
        self.assertNotIn('key', body)
        token = response.cookies[settings.AUTH_COOKIE_NAME].value
        return token, body['user']

    def create_event(self, token, title='Sunday Worship', category='worship', capacity=None):
        payload = {
            'title': title,
            'description': 'Join us.',
            'organizer': 'Lagos Christian Center',
            'date': '2026-06-01T10:00:00Z',
            'end_date': '2026-06-01T12:00:00Z',
            'location': 'Faith Tabernacle, Lagos',
            'location_lat': 6.5244,
            'location_lng': 3.3792,
            'pricing': 'free',
            'ticket_price': None,
            'category': category,
            'language': 'english',
            'age_group': 'all_ages',
        }
        if capacity is not None:
            payload['capacity'] = capacity
        response = self.client.post(
            '/api/events/',
            data=json.dumps(payload),
            content_type='application/json',
            **self.auth(token),
        )
        self.assertEqual(response.status_code, 201)
        return response.json()

    def approve_event(self, event_id):
        response = self.client.patch(
            f'/api/events/{event_id}/',
            data=json.dumps({'approval_status': 'approved'}),
            content_type='application/json',
            **self.auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_v2_contract_flow(self):
        token, user = self.register()
        auth = self.auth(token)

        login_response = self.client.post(
            '/api/auth/login/',
            data=json.dumps({'email': 'user@example.com', 'password': TEST_PASSWORD}),
            content_type='application/json',
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertIn('user', login_response.json())

        categories_response = self.client.get('/api/categories/')
        self.assertEqual(categories_response.status_code, 200)
        first_category = categories_response.json()[0]
        self.assertEqual(
            set(first_category.keys()),
            {'id', 'name', 'slug', 'icon', 'description', 'events_count', 'is_active', 'sort_order'},
        )

        event = self.create_event(token, capacity=1)
        self.assertEqual(event['approval_status'], 'pending')
        self.assertEqual(event['category']['slug'], 'worship')
        self.assertEqual(event['created_by']['id'], user['id'])
        self.assertFalse(event['is_rsvped'])

        empty_public_list = self.client.get('/api/events/')
        self.assertEqual(empty_public_list.status_code, 200)
        self.assertEqual(empty_public_list.json()['count'], 0)

        approved_event = self.approve_event(event['id'])
        self.assertEqual(approved_event['approval_status'], 'approved')

        second_event = self.create_event(token, title='Youth Conference', category='youth')
        self.approve_event(second_event['id'])

        list_response = self.client.get('/api/events/?page_size=1')
        self.assertEqual(list_response.status_code, 200)
        event_list = list_response.json()
        self.assertEqual(event_list['count'], 2)
        self.assertIsNotNone(event_list['next'])
        self.assertIsNone(event_list['previous'])
        self.assertEqual(len(event_list['results']), 1)

        search_response = self.client.get('/api/events/?search=conference&category=youth')
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.json()['count'], 1)
        self.assertEqual(search_response.json()['results'][0]['title'], 'Youth Conference')

        put_response = self.client.put(
            f'/api/events/{event["id"]}/',
            data=json.dumps({'title': 'Old update alias'}),
            content_type='application/json',
            **auth,
        )
        self.assertEqual(put_response.status_code, 405)

        like_response = self.client.post(f'/api/events/{event["id"]}/like/', **auth)
        self.assertEqual(like_response.status_code, 200)
        self.assertEqual(like_response.json()['liked'], True)
        self.assertEqual(like_response.json()['likes_count'], 1)

        save_response = self.client.post(f'/api/events/{event["id"]}/save/', **auth)
        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(save_response.json()['saved'], True)
        self.assertEqual(save_response.json()['saves_count'], 1)

        rsvp_response = self.client.post(f'/api/events/{event["id"]}/rsvp/', **auth)
        self.assertEqual(rsvp_response.status_code, 200)
        self.assertEqual(rsvp_response.json()['rsvped'], True)
        self.assertEqual(rsvp_response.json()['rsvp_count'], 1)

        other_token, _other_user = self.register(email='other@example.com', username='other')
        full_response = self.client.post(f'/api/events/{event["id"]}/rsvp/', **self.auth(other_token))
        self.assertEqual(full_response.status_code, 400)
        self.assertEqual(full_response.json()['detail'], 'This event is at full capacity.')

        attending_response = self.client.get('/api/events/attending/', **auth)
        self.assertEqual(attending_response.status_code, 200)
        self.assertEqual(len(attending_response.json()), 1)

        attendees_response = self.client.get(f'/api/events/{event["id"]}/attendees/', **auth)
        self.assertEqual(attendees_response.status_code, 200)
        self.assertEqual(attendees_response.json()['count'], 1)
        self.assertIn('rsvped_at', attendees_response.json()['results'][0])

        related_response = self.client.get(f'/api/events/{event["id"]}/related/')
        self.assertEqual(related_response.status_code, 200)
        self.assertEqual(related_response.json()['count'], 0)

        profile_response = self.client.get('/api/auth/user/', **auth)
        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(profile_response.json()['events_created_count'], 2)
        self.assertEqual(profile_response.json()['events_liked_count'], 1)
        self.assertEqual(profile_response.json()['events_saved_count'], 1)
        self.assertEqual(profile_response.json()['events_attending_count'], 1)

        public_user_response = self.client.get(f'/api/users/{user["id"]}/')
        self.assertEqual(public_user_response.status_code, 200)
        self.assertEqual(public_user_response.json()['events_created_count'], 2)

        notification_count_response = self.client.get('/api/notifications/unread-count/', **auth)
        self.assertEqual(notification_count_response.status_code, 200)
        self.assertGreaterEqual(notification_count_response.json()['count'], 2)

        notifications_response = self.client.get('/api/notifications/', **auth)
        self.assertEqual(notifications_response.status_code, 200)
        notification = notifications_response.json()['results'][0]
        self.assertIn('type', notification)

        read_response = self.client.post(f'/api/notifications/{notification["id"]}/read/', **auth)
        self.assertEqual(read_response.status_code, 200)
        self.assertTrue(read_response.json()['is_read'])

        read_all_response = self.client.post('/api/notifications/read-all/', **auth)
        self.assertEqual(read_all_response.status_code, 200)
        self.assertIn('updated', read_all_response.json())

        delete_response = self.client.delete(f'/api/notifications/{notification["id"]}/', **auth)
        self.assertEqual(delete_response.status_code, 204)

        liked_response = self.client.get('/api/events/liked/', **auth)
        self.assertEqual(liked_response.status_code, 200)
        self.assertEqual(len(liked_response.json()), 1)

        logout_response = self.client.post('/api/auth/logout/', **auth)
        self.assertEqual(logout_response.status_code, 200)
        self.assertEqual(logout_response.json()['detail'], 'Logged out successfully.')

    def test_admin_can_manage_categories(self):
        response = self.client.post(
            '/api/categories/',
            data=json.dumps({'name': 'Arts', 'slug': 'arts', 'icon': 'camera'}),
            content_type='application/json',
            **self.auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 201)
        category_id = response.json()['id']

        patch_response = self.client.patch(
            f'/api/categories/{category_id}/',
            data=json.dumps({'sort_order': 99}),
            content_type='application/json',
            **self.auth(self.admin_token),
        )
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(patch_response.json()['sort_order'], 99)

        delete_response = self.client.delete(f'/api/categories/{category_id}/', **self.auth(self.admin_token))
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(delete_response.json()['is_active'])

    def test_unknown_api_route_returns_json_404(self):
        response = self.client.get('/api/nope/')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {'detail': 'Not found.'})


@NO_EMAIL
class CookieAuthCsrfTests(ApiTestCase):
    """Verifies the cookie-based auth + CSRF protection actually does something,
    using a client that enforces CSRF like a real browser would (the default
    test Client silently skips CSRF checks)."""

    def setUp(self):
        super().setUp()
        self.client = Client(enforce_csrf_checks=True)

    def register_payload(self, email='cookie@example.com', username='cookieuser'):
        return json.dumps({
            'email': email,
            'password': TEST_PASSWORD,
            'first_name': 'Cookie',
            'last_name': 'User',
            'username': username,
        })

    def test_register_without_csrf_token_is_rejected(self):
        response = self.client.post(
            '/api/auth/register/',
            data=self.register_payload(),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_register_sets_httponly_cookie_and_csrf_protected_flow_works(self):
        csrf_response = self.client.get('/api/auth/csrf/')
        self.assertEqual(csrf_response.status_code, 200)
        csrf_token = csrf_response.cookies['csrftoken'].value

        register_response = self.client.post(
            '/api/auth/register/',
            data=self.register_payload(),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(register_response.status_code, 201)
        self.assertNotIn('key', register_response.json())

        auth_cookie = register_response.cookies[settings.AUTH_COOKIE_NAME]
        self.assertTrue(auth_cookie['httponly'])

        # No Authorization header — must be authenticated purely via the cookie
        # the test client now carries.
        me_response = self.client.get('/api/auth/user/')
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()['email'], 'cookie@example.com')

        logout_response = self.client.post(
            '/api/auth/logout/',
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(logout_response.status_code, 200)

        me_after_logout = self.client.get('/api/auth/user/')
        self.assertEqual(me_after_logout.status_code, 401)

    def test_csrf_endpoint_returns_token_usable_as_header(self):
        # Cross-site SPAs cannot read the API's cookie, so they rely on the
        # token in the response body instead.
        csrf_response = self.client.get('/api/auth/csrf/')
        body_token = csrf_response.json()['csrfToken']
        self.assertTrue(body_token)

        register_response = self.client.post(
            '/api/auth/register/',
            data=self.register_payload(),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=body_token,
        )
        self.assertEqual(register_response.status_code, 201)

    def test_csrf_failure_returns_json_with_code(self):
        self.client.get('/api/auth/csrf/')
        response = self.client.post(
            '/api/auth/register/',
            data=self.register_payload(),
            content_type='application/json',
            HTTP_X_CSRFTOKEN='wrong-token-value-wrong-token-value',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'csrf_failed')


@override_settings(ZEPTOMAIL_API_KEY='test-key', EMAIL_SEND_ASYNC=True)
class EmailDeliveryTests(TestCase):
    def send(self):
        from .views import send_template_email
        send_template_email('Hi', 'welcome', {'first_name': 'A', 'browse_url': 'x'}, 'alice@example.com')

    @mock.patch('api.views.http_requests.post')
    def test_email_is_sent_only_after_commit(self, post):
        post.return_value.ok = True
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.send()
        post.assert_not_called()
        self.assertEqual(len(callbacks), 1)

    @mock.patch('api.views._email_executor')
    def test_email_is_delivered_off_the_request_thread(self, executor):
        with self.captureOnCommitCallbacks(execute=True):
            self.send()
        executor.submit.assert_called_once()

    @override_settings(EMAIL_SEND_ASYNC=False)
    @mock.patch('api.views.http_requests.post')
    def test_failed_send_logs_masked_recipient(self, post):
        post.return_value.ok = False
        post.return_value.status_code = 401
        post.return_value.text = 'denied'
        with self.assertLogs('api', level='ERROR') as logs:
            self.send()
        self.assertNotIn('alice@example.com', logs.output[0])
        self.assertIn('a***@example.com', logs.output[0])


@NO_EMAIL
class PasswordSecurityTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.user = User.objects.create_user(email='pw@example.com', username='pw', password=TEST_PASSWORD)

    def post(self, path, payload, token=None):
        extra = {'HTTP_AUTHORIZATION': f'Token {token}'} if token else {}
        return self.client.post(path, data=json.dumps(payload), content_type='application/json', **extra)

    def request_reset(self, raw_token):
        with mock.patch('api.views.secrets.token_urlsafe', return_value=raw_token):
            response = self.post('/api/auth/password/reset/', {'email': 'pw@example.com'})
        self.assertEqual(response.status_code, 200)

    def confirm_reset(self, raw_token, password='new-quiet-harbour-77'):
        return self.post('/api/auth/password/reset/confirm/', {
            'token': raw_token, 'new_password1': password, 'new_password2': password,
        })

    def test_register_rejects_common_password(self):
        response = self.post('/api/auth/register/', {'email': 'weak@example.com', 'password': 'password123'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('password', response.json())

    def test_reset_token_is_stored_hashed(self):
        self.request_reset('raw-reset-token')
        self.assertFalse(PasswordResetToken.objects.filter(token='raw-reset-token').exists())
        self.assertTrue(PasswordResetToken.objects.filter(user=self.user).exists())

    def test_reset_revokes_sessions_and_is_single_use(self):
        _, session = AuthToken.objects.create(user=self.user)
        self.request_reset('raw-reset-token')

        self.assertEqual(self.confirm_reset('raw-reset-token').status_code, 200)
        self.assertEqual(self.client.get('/api/auth/user/', HTTP_AUTHORIZATION=f'Token {session}').status_code, 401)
        self.assertEqual(self.confirm_reset('raw-reset-token', 'another-quiet-harbour-9').status_code, 400)

    def test_new_reset_link_invalidates_older_one(self):
        self.request_reset('first-token')
        self.request_reset('second-token')
        self.assertEqual(self.confirm_reset('first-token').status_code, 400)
        self.assertEqual(self.confirm_reset('second-token').status_code, 200)

    def test_change_password_signs_out_other_sessions_only(self):
        _, current = AuthToken.objects.create(user=self.user)
        _, other = AuthToken.objects.create(user=self.user)
        response = self.post('/api/auth/password/change/', {
            'old_password': TEST_PASSWORD,
            'new_password1': 'new-quiet-harbour-77',
            'new_password2': 'new-quiet-harbour-77',
        }, token=current)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/api/auth/user/', HTTP_AUTHORIZATION=f'Token {current}').status_code, 200)
        self.assertEqual(self.client.get('/api/auth/user/', HTTP_AUTHORIZATION=f'Token {other}').status_code, 401)

    def test_logout_with_dead_token_still_clears_cookie(self):
        self.client.cookies[settings.AUTH_COOKIE_NAME] = 'expired-or-bogus'
        response = self.client.post('/api/auth/logout/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.cookies[settings.AUTH_COOKIE_NAME].value, '')


@NO_EMAIL
class RateLimitTests(ApiTestCase):
    def test_client_ip_uses_rightmost_untrusted_forwarded_entry(self):
        from django.test import RequestFactory

        from .ratelimit import client_ip

        request = RequestFactory().get('/', HTTP_X_FORWARDED_FOR='6.6.6.6, 203.0.113.9', REMOTE_ADDR='10.0.0.1')
        with self.settings(NUM_TRUSTED_PROXIES=1):
            # 6.6.6.6 is client-supplied and spoofable; the proxy appended 203.0.113.9.
            self.assertEqual(client_ip(request), '203.0.113.9')
        with self.settings(NUM_TRUSTED_PROXIES=0):
            self.assertEqual(client_ip(request), '10.0.0.1')

    def test_login_is_limited_per_account_across_ips(self):
        payload = json.dumps({'email': 'victim@example.com', 'password': 'wrong'})
        statuses = []
        with self.settings(NUM_TRUSTED_PROXIES=1):
            for attempt in range(6):
                response = self.client.post(
                    '/api/auth/login/', data=payload, content_type='application/json',
                    HTTP_X_FORWARDED_FOR=f'198.51.100.{attempt}',
                )
                statuses.append(response.status_code)
        self.assertEqual(statuses[:5], [400] * 5)
        self.assertEqual(statuses[5], 429)


def make_image_bytes(size=(40, 30), fmt='PNG'):
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new('RGB', size, 'purple').save(buffer, format=fmt)
    return buffer.getvalue()


@NO_EMAIL
class EventValidationTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(email='owner@example.com', username='owner', password=TEST_PASSWORD)
        self.admin = User.objects.create_user(email='mod@example.com', username='mod', password=TEST_PASSWORD, is_staff=True)
        _, self.owner_token = AuthToken.objects.create(user=self.owner)
        _, self.admin_token = AuthToken.objects.create(user=self.admin)

    def auth(self, token):
        return {'HTTP_AUTHORIZATION': f'Token {token}'}

    def payload(self, **overrides):
        payload = {
            'title': 'Choir Night', 'description': 'Songs.', 'date': '2030-06-01T18:00:00Z',
            'location': 'Lagos', 'pricing': 'free', 'category': 'worship',
            'language': 'english', 'age_group': 'all_ages',
        }
        payload.update(overrides)
        return payload

    def create(self, **overrides):
        return self.client.post('/api/events/', data=json.dumps(self.payload(**overrides)),
                                content_type='application/json', **self.auth(self.owner_token))

    def patch(self, event_id, payload, token):
        return self.client.patch(f'/api/events/{event_id}/', data=json.dumps(payload),
                                 content_type='application/json', **self.auth(token))

    def test_rejects_invalid_choices_lengths_and_ranges(self):
        response = self.create(pricing='banana', language='klingon', title='x' * 300, location_lat=123)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()), {'pricing', 'language', 'title', 'location_lat'})

    def test_rejects_negative_ticket_price(self):
        response = self.create(pricing='paid', ticket_price=-5)
        self.assertEqual(response.status_code, 400)
        self.assertIn('ticket_price', response.json())

    def test_non_object_json_body_is_a_400_not_a_500(self):
        response = self.client.post('/api/events/', data='[1, 2]', content_type='application/json',
                                    **self.auth(self.owner_token))
        self.assertEqual(response.status_code, 400)

    def test_multipart_patch_updates_fields_and_image(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test.client import MULTIPART_CONTENT, encode_multipart, BOUNDARY

        event_id = self.create().json()['id']
        body = encode_multipart(BOUNDARY, {
            'title': 'Renamed via multipart',
            'image': SimpleUploadedFile('cover.png', make_image_bytes(), content_type='image/png'),
        })
        with self.settings(MEDIA_ROOT=self.media_dir()):
            response = self.client.patch(f'/api/events/{event_id}/', data=body, content_type=MULTIPART_CONTENT,
                                         **self.auth(self.owner_token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['title'], 'Renamed via multipart')
        self.assertIsNotNone(response.json()['image'])

    def test_rejects_decompression_bomb_dimensions(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from .views import validate_and_process_image

        with self.settings(MEDIA_ROOT=self.media_dir()), mock.patch('api.views.MAX_IMAGE_PIXELS', 100):
            upload = SimpleUploadedFile('big.png', make_image_bytes((20, 20)), content_type='image/png')
            _image, errors = validate_and_process_image(upload)
        self.assertEqual(errors, ['Image dimensions are too large.'])

    def test_organizer_edit_sends_approved_event_back_to_review(self):
        event_id = self.create().json()['id']
        self.assertEqual(self.patch(event_id, {'approval_status': 'approved'}, self.admin_token).status_code, 200)

        response = self.patch(event_id, {'title': 'Something else entirely'}, self.owner_token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['approval_status'], 'pending')
        self.assertEqual(self.client.get('/api/events/').json()['count'], 0)

    def test_organizer_cannot_self_approve(self):
        event_id = self.create().json()['id']
        response = self.patch(event_id, {'approval_status': 'approved', 'is_featured': True}, self.owner_token)
        self.assertEqual(response.json()['approval_status'], 'pending')
        self.assertFalse(response.json()['is_featured'])

    def test_other_user_cannot_modify_event(self):
        event_id = self.create().json()['id']
        stranger = User.objects.create_user(email='x@example.com', username='x', password=TEST_PASSWORD)
        _, stranger_token = AuthToken.objects.create(user=stranger)
        self.assertEqual(self.patch(event_id, {'approval_status': 'approved'}, self.admin_token).status_code, 200)
        self.assertEqual(self.patch(event_id, {'title': 'pwned'}, stranger_token).status_code, 403)
        response = self.client.delete(f'/api/events/{event_id}/', **self.auth(stranger_token))
        self.assertEqual(response.status_code, 403)

    def test_pending_event_hidden_from_other_users(self):
        event_id = self.create().json()['id']
        self.assertEqual(self.client.get(f'/api/events/{event_id}/').status_code, 404)
        self.assertEqual(self.client.post(f'/api/events/{event_id}/rsvp/', **self.auth(self.admin_token)).status_code, 200)

    def media_dir(self):
        import tempfile

        path = tempfile.mkdtemp()
        self.addCleanup(__import__('shutil').rmtree, path, True)
        return path


@NO_EMAIL
class ProfileValidationTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email='me@example.com', username='me', password=TEST_PASSWORD)
        _, self.token = AuthToken.objects.create(user=self.user)

    def patch(self, payload):
        return self.client.patch('/api/auth/user/', data=json.dumps(payload), content_type='application/json',
                                 HTTP_AUTHORIZATION=f'Token {self.token}')

    def test_rejects_wrong_types_without_saving(self):
        response = self.patch({'max_distance_km': 'abc', 'email_notifications': 'yes', 'first_name': 'Ada'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()), {'max_distance_km', 'email_notifications'})
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, '')

    def test_rejects_unknown_preference_values(self):
        response = self.patch({'preferred_languages': ['english', 'klingon']})
        self.assertEqual(response.status_code, 400)

    def test_valid_update_succeeds(self):
        response = self.patch({'preferred_languages': ['english', 'yoruba'], 'max_distance_km': 25, 'city': ' Ikeja '})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['city'], 'Ikeja')

    def test_cannot_change_email_or_staff_flag(self):
        self.patch({'email': 'new@example.com', 'is_staff': True})
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'me@example.com')
        self.assertFalse(self.user.is_staff)

    def test_register_rejects_invalid_email(self):
        response = self.client.post('/api/auth/register/', data=json.dumps({
            'email': 'not-an-email', 'password': TEST_PASSWORD}), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.json())


@NO_EMAIL
class QueryEfficiencyTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        from .models import Category, Event

        self.user = User.objects.create_user(email='q@example.com', username='q', password=TEST_PASSWORD)
        _, self.token = AuthToken.objects.create(user=self.user)
        self.category = Category.objects.get(slug='worship')
        self.make = lambda n: [
            Event.objects.create(
                title=f'E{i}', description='d', date='2030-01-01T10:00:00Z', location='L', pricing='free',
                category=self.category, language='english', age_group='all_ages', created_by=self.user,
                approval_status='approved',
            )
            for i in range(n)
        ]

    def list_query_count(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get('/api/events/', HTTP_AUTHORIZATION=f'Token {self.token}')
        self.assertEqual(response.status_code, 200)
        return len(ctx), response.json()

    def test_event_list_query_count_does_not_grow_with_page_size(self):
        self.make(1)
        one, _ = self.list_query_count()
        self.make(9)
        ten, body = self.list_query_count()
        self.assertEqual(one, ten)
        self.assertEqual(body['count'], 10)

    def test_annotated_flags_match_viewer_state(self):
        event = self.make(1)[0]
        self.client.post(f'/api/events/{event.id}/like/', HTTP_AUTHORIZATION=f'Token {self.token}')
        _, body = self.list_query_count()
        item = body['results'][0]
        self.assertTrue(item['is_liked'])
        self.assertFalse(item['is_saved'])
        self.assertEqual(item['likes_count'], 1)
        self.assertEqual(item['rsvp_count'], 0)

    def test_rsvp_toggle_respects_capacity(self):
        event = self.make(1)[0]
        event.capacity = 1
        event.save()
        other = User.objects.create_user(email='o@example.com', username='o', password=TEST_PASSWORD)
        _, other_token = AuthToken.objects.create(user=other)
        self.assertEqual(self.client.post(f'/api/events/{event.id}/rsvp/', HTTP_AUTHORIZATION=f'Token {self.token}').json()['rsvped'], True)
        self.assertEqual(self.client.post(f'/api/events/{event.id}/rsvp/', HTTP_AUTHORIZATION=f'Token {other_token}').status_code, 400)
        self.assertEqual(self.client.post(f'/api/events/{event.id}/rsvp/', HTTP_AUTHORIZATION=f'Token {self.token}').json()['rsvped'], False)
        self.assertEqual(self.client.post(f'/api/events/{event.id}/rsvp/', HTTP_AUTHORIZATION=f'Token {other_token}').status_code, 200)


class OperationalTests(TestCase):
    def test_responses_carry_request_id_and_honour_safe_incoming_ids(self):
        generated = self.client.get('/api/health/')
        self.assertRegex(generated['X-Request-ID'], r'^[0-9a-f]{32}$')
        echoed = self.client.get('/api/health/', HTTP_X_REQUEST_ID='abc-123')
        self.assertEqual(echoed['X-Request-ID'], 'abc-123')
        unsafe = self.client.get('/api/health/', HTTP_X_REQUEST_ID='bad id\ninjected')
        self.assertNotIn('injected', unsafe['X-Request-ID'])

    def test_readiness_reports_database_state(self):
        self.assertEqual(self.client.get('/api/health/ready/').json(), {'status': 'ok', 'database': 'ok'})
        with mock.patch('api.views.connection.cursor', side_effect=__import__('django.db', fromlist=['OperationalError']).OperationalError):
            self.assertEqual(self.client.get('/api/health/ready/').status_code, 503)

    def test_unhandled_error_returns_json_with_request_id(self):
        client = Client(raise_request_exception=False)
        with mock.patch('api.views.filtered_events', side_effect=RuntimeError('boom')):
            response = client.get('/api/events/', HTTP_X_REQUEST_ID='trace-me')
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()['request_id'], 'trace-me')


class ProductionGuardTests(TestCase):
    @override_settings(DEBUG=False, FRONTEND_URL='http://localhost:5173', CLOUDINARY_URL='', ZEPTOMAIL_API_KEY='',
                       CORS_ALLOWED_ORIGINS=['https://app.example.com'], CSRF_TRUSTED_ORIGINS=[])
    def test_deploy_checks_flag_broken_production_config(self):
        from .checks import production_configuration

        ids = {warning.id for warning in production_configuration(None)}
        self.assertEqual(ids, {'eventlight.W001', 'eventlight.W003', 'eventlight.W004', 'eventlight.W005'})

    @override_settings(DEBUG=False)
    def test_seed_command_refuses_production(self):
        from django.core.management import CommandError, call_command

        with self.assertRaises(CommandError):
            call_command('seed_demo_data')


@override_settings(SECURE_SSL_REDIRECT=True, SECURE_REDIRECT_EXEMPT=[r'^api/health/'])
class SslRedirectTests(TestCase):
    def test_health_probes_are_not_redirected_but_api_is(self):
        self.assertEqual(self.client.get('/api/health/').status_code, 200)
        self.assertEqual(self.client.get('/api/health/ready/').status_code, 200)
        self.assertEqual(self.client.get('/api/events/').status_code, 301)


@NO_EMAIL
class EventReminderTests(ApiTestCase):
    def test_reminds_rsvped_and_saving_users_once_respecting_preferences(self):
        from datetime import timedelta

        from django.core.management import call_command
        from django.utils import timezone

        from .models import RSVP, Category, Event, EventSave, Notification

        organizer = User.objects.create_user(email='org@example.com', username='org', password=TEST_PASSWORD)
        going = User.objects.create_user(email='go@example.com', username='go', password=TEST_PASSWORD)
        saver = User.objects.create_user(email='sv@example.com', username='sv', password=TEST_PASSWORD)
        opted_out = User.objects.create_user(email='no@example.com', username='no', password=TEST_PASSWORD,
                                             event_reminders=False)

        def event(hours_ahead, status='approved'):
            return Event.objects.create(
                title='Soon', description='d', date=timezone.now() + timedelta(hours=hours_ahead), location='L',
                pricing='free', category=Category.objects.get(slug='worship'), language='english',
                age_group='all_ages', created_by=organizer, approval_status=status,
            )

        soon, later, pending = event(3), event(72), event(3, status='pending')
        for target in (soon, later, pending):
            RSVP.objects.create(user=going, event=target)
            RSVP.objects.create(user=opted_out, event=target)
        EventSave.objects.create(user=saver, event=soon)

        call_command('send_event_reminders', stdout=__import__('io').StringIO())
        call_command('send_event_reminders', stdout=__import__('io').StringIO())

        reminders = Notification.objects.filter(type='reminder')
        self.assertEqual(
            sorted(reminders.values_list('user__username', 'event_id')),
            [('go', soon.id), ('sv', soon.id)],
        )
