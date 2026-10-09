import json
from unittest import mock

from django.conf import settings
from django.test import Client, TestCase, override_settings
from knox.models import AuthToken

from .models import PasswordResetToken, User


# The developer's .env may hold a real ZeptoMail key; tests must never send mail.
NO_EMAIL = override_settings(ZEPTOMAIL_API_KEY='')
TEST_PASSWORD = 'quiet-harbour-lantern-42'


@NO_EMAIL
class ApiContractTests(TestCase):
    def setUp(self):
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
class CookieAuthCsrfTests(TestCase):
    """Verifies the cookie-based auth + CSRF protection actually does something,
    using a client that enforces CSRF like a real browser would (the default
    test Client silently skips CSRF checks)."""

    def setUp(self):
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
class PasswordSecurityTests(TestCase):
    def setUp(self):
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
