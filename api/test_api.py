import hashlib
import io
import json
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from knox.models import AuthToken
from PIL import Image

from .models import (
    Category,
    Event,
    EventLike,
    EventSave,
    Notification,
    PasswordResetToken,
    RSVP,
    User,
)


FUTURE_DATE = (timezone.now() + timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
FUTURE_END = (timezone.now() + timedelta(days=30, hours=3)).strftime('%Y-%m-%dT%H:%M:%SZ')
PAST_DATE = '2020-01-01T10:00:00Z'
# Must pass AUTH_PASSWORD_VALIDATORS (common passwords such as 'password123' are rejected).
TEST_PASSWORD = 'quiet-harbour-lantern-42'


def make_image_file(format='JPEG', size=(100, 100), color='red'):
    """Create an in-memory image file for upload tests."""
    img = Image.new('RGB', size, color=color)
    buf = io.BytesIO()
    img.save(buf, format=format)
    return SimpleUploadedFile(
        'test.jpg',
        buf.getvalue(),
        content_type='image/jpeg',
    )


@override_settings(RATELIMIT_ENABLE=False)
# A developer's .env may hold a real ZeptoMail key; tests must never send mail.
@override_settings(ZEPTOMAIL_API_KEY='')
class BaseTestCase(TestCase):
    """Shared fixtures and helpers for all test classes."""

    def setUp(self):
        # Rate-limit counters live in the cache and would leak between tests.
        cache.clear()
        self.client = Client()
        self.admin = User.objects.create_user(
            email='admin@example.com',
            username='admin',
            password=TEST_PASSWORD,
            is_staff=True,
        )
        _, self.admin_token = AuthToken.objects.create(user=self.admin)

        # Migrations already seed categories (worship, youth, etc.).
        # Use get_or_create to avoid duplicate slug errors.
        self.category, _ = Category.objects.get_or_create(
            slug='worship',
            defaults={'name': 'Worship', 'icon': 'heart', 'description': 'Worship gatherings', 'sort_order': 1},
        )
        Category.objects.get_or_create(
            slug='youth',
            defaults={'name': 'Youth', 'icon': 'award', 'sort_order': 2},
        )

    def auth(self, token):
        return {'HTTP_AUTHORIZATION': f'Token {token}'}

    def clear_auth(self):
        """Clear cookies so subsequent requests are truly unauthenticated."""
        self.client = Client()

    def register(self, email='user@example.com', username='johndoe', password=TEST_PASSWORD):
        response = self.client.post(
            '/api/auth/register/',
            data=json.dumps({
                'email': email,
                'password': password,
                'first_name': 'John',
                'last_name': 'Doe',
                'username': username,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        # The token is only ever delivered as the httpOnly cookie, never in the body.
        return response.cookies[settings.AUTH_COOKIE_NAME].value, body['user']

    def create_event(self, token, **overrides):
        payload = {
            'title': 'Sunday Worship',
            'description': 'Join us.',
            'organizer': 'Lagos Christian Center',
            'date': FUTURE_DATE,
            'end_date': FUTURE_END,
            'location': 'Faith Tabernacle, Lagos',
            'location_lat': 6.5244,
            'location_lng': 3.3792,
            'pricing': 'free',
            'ticket_price': None,
            'category': 'worship',
            'language': 'english',
            'age_group': 'all_ages',
        }
        payload.update(overrides)
        response = self.client.post(
            '/api/events/',
            data=json.dumps(payload),
            content_type='application/json',
            **self.auth(token),
        )
        return response

    def approve_event(self, event_id):
        response = self.client.patch(
            f'/api/events/{event_id}/',
            data=json.dumps({'approval_status': 'approved'}),
            content_type='application/json',
            **self.auth(self.admin_token),
        )
        return response


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class AuthTests(BaseTestCase):
    def test_register_returns_token_and_user(self):
        token, user = self.register()
        self.assertTrue(token)
        self.assertEqual(user['email'], 'user@example.com')
        self.assertEqual(user['first_name'], 'John')

    def test_register_sets_auth_cookie(self):
        response = self.client.post(
            '/api/auth/register/',
            data=json.dumps({
                'email': 'cookie@example.com',
                'password': TEST_PASSWORD,
                'username': 'cookieuser',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn('auth_token', response.cookies)
        self.assertTrue(response.cookies['auth_token']['httponly'])

    def test_register_duplicate_email_rejected(self):
        self.register()
        response = self.client.post(
            '/api/auth/register/',
            data=json.dumps({
                'email': 'user@example.com',
                'password': TEST_PASSWORD,
                'username': 'other',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.json())

    def test_register_short_password_rejected(self):
        response = self.client.post(
            '/api/auth/register/',
            data=json.dumps({
                'email': 'short@example.com',
                'password': 'short',
                'username': 'shortuser',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('password', response.json())

    def test_register_missing_email(self):
        response = self.client.post(
            '/api/auth/register/',
            data=json.dumps({'password': TEST_PASSWORD, 'username': 'noemail'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.json())

    def test_register_invalid_json(self):
        response = self.client.post(
            '/api/auth/register/',
            data='not json',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['detail'], 'Invalid JSON.')

    def test_register_get_method_not_allowed(self):
        response = self.client.get('/api/auth/register/')
        self.assertEqual(response.status_code, 405)

    def test_login_valid_credentials(self):
        self.register()
        response = self.client.post(
            '/api/auth/login/',
            data=json.dumps({'email': 'user@example.com', 'password': TEST_PASSWORD}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('key', response.json())
        self.assertIn('user', response.json())

    def test_login_sets_auth_cookie(self):
        self.register()
        response = self.client.post(
            '/api/auth/login/',
            data=json.dumps({'email': 'user@example.com', 'password': TEST_PASSWORD}),
            content_type='application/json',
        )
        self.assertIn('auth_token', response.cookies)
        self.assertTrue(response.cookies['auth_token']['httponly'])

    def test_login_invalid_credentials(self):
        self.register()
        response = self.client.post(
            '/api/auth/login/',
            data=json.dumps({'email': 'user@example.com', 'password': 'wrong'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['detail'], 'Invalid credentials.')

    def test_login_case_insensitive_email(self):
        self.register(email='Test@Example.com')
        response = self.client.post(
            '/api/auth/login/',
            data=json.dumps({'email': 'test@example.com', 'password': TEST_PASSWORD}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

    def test_logout_clears_cookie(self):
        token, _ = self.register()
        response = self.client.post('/api/auth/logout/', **self.auth(token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.cookies['auth_token'].value, '')

    def test_logout_without_auth_still_succeeds(self):
        # Logout is idempotent so a browser holding an expired cookie can always clear it.
        response = self.client.post('/api/auth/logout/')
        self.assertEqual(response.status_code, 200)

    def test_logout_invalidates_token(self):
        token, _ = self.register()
        self.client.post('/api/auth/logout/', **self.auth(token))
        response = self.client.get('/api/auth/user/', **self.auth(token))
        self.assertEqual(response.status_code, 401)

    def test_cookie_authenticates_without_header(self):
        token, _ = self.register()
        self.client.cookies['auth_token'] = token
        response = self.client.get('/api/auth/user/')
        self.assertEqual(response.status_code, 200)

    def test_current_user_get(self):
        token, user = self.register()
        response = self.client.get('/api/auth/user/', **self.auth(token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['email'], user['email'])

    def test_current_user_without_auth(self):
        response = self.client.get('/api/auth/user/')
        self.assertEqual(response.status_code, 401)

    def test_current_user_patch(self):
        token, _ = self.register()
        response = self.client.patch(
            '/api/auth/user/',
            data=json.dumps({'first_name': 'Updated', 'city': 'Abuja'}),
            content_type='application/json',
            **self.auth(token),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['first_name'], 'Updated')
        self.assertEqual(response.json()['city'], 'Abuja')

    def test_current_user_patch_duplicate_username(self):
        self.register(email='other@example.com', username='taken')
        token, _ = self.register(email='me@example.com', username='me')
        response = self.client.patch(
            '/api/auth/user/',
            data=json.dumps({'username': 'taken'}),
            content_type='application/json',
            **self.auth(token),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('username', response.json())

    def test_change_password_success(self):
        token, _ = self.register()
        response = self.client.post(
            '/api/auth/password/change/',
            data=json.dumps({
                'old_password': TEST_PASSWORD,
                'new_password1': 'newpassword456',
                'new_password2': 'newpassword456',
            }),
            content_type='application/json',
            **self.auth(token),
        )
        self.assertEqual(response.status_code, 200)

    def test_change_password_wrong_old(self):
        token, _ = self.register()
        response = self.client.post(
            '/api/auth/password/change/',
            data=json.dumps({
                'old_password': 'wrong',
                'new_password1': 'newpassword456',
                'new_password2': 'newpassword456',
            }),
            content_type='application/json',
            **self.auth(token),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('old_password', response.json())

    def test_change_password_mismatch(self):
        token, _ = self.register()
        response = self.client.post(
            '/api/auth/password/change/',
            data=json.dumps({
                'old_password': TEST_PASSWORD,
                'new_password1': 'newpassword456',
                'new_password2': 'different',
            }),
            content_type='application/json',
            **self.auth(token),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('new_password2', response.json())

    def test_change_password_too_short(self):
        token, _ = self.register()
        response = self.client.post(
            '/api/auth/password/change/',
            data=json.dumps({
                'old_password': TEST_PASSWORD,
                'new_password1': 'short',
                'new_password2': 'short',
            }),
            content_type='application/json',
            **self.auth(token),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('new_password1', response.json())

    def test_change_password_invalidates_other_tokens(self):
        token, _ = self.register()
        user_obj = User.objects.get(email='user@example.com')
        _, token2 = AuthToken.objects.create(user=user_obj)

        self.client.post(
            '/api/auth/password/change/',
            data=json.dumps({
                'old_password': TEST_PASSWORD,
                'new_password1': 'newpassword456',
                'new_password2': 'newpassword456',
            }),
            content_type='application/json',
            **self.auth(token),
        )

        # Current token still works.
        r1 = self.client.get('/api/auth/user/', **self.auth(token))
        self.assertEqual(r1.status_code, 200)
        # Other token is invalidated.
        r2 = self.client.get('/api/auth/user/', **self.auth(token2))
        self.assertEqual(r2.status_code, 401)


# ---------------------------------------------------------------------------
# Password reset tests
# ---------------------------------------------------------------------------

class PasswordResetTests(BaseTestCase):
    def test_password_reset_unknown_email_returns_same_response(self):
        response = self.client.post(
            '/api/auth/password/reset/',
            data=json.dumps({'email': 'nonexistent@example.com'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('reset link', response.json()['detail'])

    def test_password_reset_known_email_creates_token(self):
        self.register(email='reset@example.com')
        response = self.client.post(
            '/api/auth/password/reset/',
            data=json.dumps({'email': 'reset@example.com'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        token = PasswordResetToken.objects.filter(user__email='reset@example.com', is_used=False).first()
        self.assertIsNotNone(token)
        # Token is hashed in DB.
        self.assertEqual(len(token.token), 64)

    def test_password_reset_missing_email(self):
        response = self.client.post(
            '/api/auth/password/reset/',
            data=json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.json())

    def test_password_reset_invalidates_previous_tokens(self):
        self.register(email='reset@example.com')
        self.client.post(
            '/api/auth/password/reset/',
            data=json.dumps({'email': 'reset@example.com'}),
            content_type='application/json',
        )
        first_count = PasswordResetToken.objects.filter(user__email='reset@example.com', is_used=False).count()
        self.assertEqual(first_count, 1)

        self.client.post(
            '/api/auth/password/reset/',
            data=json.dumps({'email': 'reset@example.com'}),
            content_type='application/json',
        )
        unused = PasswordResetToken.objects.filter(user__email='reset@example.com', is_used=False).count()
        self.assertEqual(unused, 1)
        used = PasswordResetToken.objects.filter(user__email='reset@example.com', is_used=True).count()
        self.assertEqual(used, 1)

    def test_password_reset_confirm_success(self):
        user = User.objects.create_user(
            email='confirm@example.com',
            username='confirm',
            password='oldpassword123',
        )
        _, old_token = AuthToken.objects.create(user=user)

        raw_token = secrets.token_urlsafe(32)
        PasswordResetToken.objects.create(user=user, token=hashlib.sha256(raw_token.encode()).hexdigest())

        response = self.client.post(
            '/api/auth/password/reset/confirm/',
            data=json.dumps({
                'token': raw_token,
                'new_password1': 'newpassword456',
                'new_password2': 'newpassword456',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        # Token is marked used.
        reset_token = PasswordResetToken.objects.get(user=user)
        self.assertTrue(reset_token.is_used)

        # Old auth token is invalidated.
        r = self.client.get('/api/auth/user/', HTTP_AUTHORIZATION=f'Token {old_token}')
        self.assertEqual(r.status_code, 401)

        # Can login with new password.
        r = self.client.post(
            '/api/auth/login/',
            data=json.dumps({'email': 'confirm@example.com', 'password': 'newpassword456'}),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 200)

    def test_password_reset_confirm_expired_token(self):
        user = User.objects.create_user(
            email='expired@example.com',
            username='expired',
            password='oldpassword123',
        )
        raw_token = secrets.token_urlsafe(32)
        token = PasswordResetToken.objects.create(user=user, token=hashlib.sha256(raw_token.encode()).hexdigest())
        # Make it expired.
        token.created_at = timezone.now() - timedelta(hours=2)
        token.save(update_fields=['created_at'])

        response = self.client.post(
            '/api/auth/password/reset/confirm/',
            data=json.dumps({
                'token': raw_token,
                'new_password1': 'newpassword456',
                'new_password2': 'newpassword456',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('token', response.json())

    def test_password_reset_confirm_already_used(self):
        user = User.objects.create_user(
            email='used@example.com',
            username='used',
            password='oldpassword123',
        )
        raw_token = secrets.token_urlsafe(32)
        PasswordResetToken.objects.create(
            user=user,
            token=hashlib.sha256(raw_token.encode()).hexdigest(),
            is_used=True,
        )
        response = self.client.post(
            '/api/auth/password/reset/confirm/',
            data=json.dumps({
                'token': raw_token,
                'new_password1': 'newpassword456',
                'new_password2': 'newpassword456',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('token', response.json())

    def test_password_reset_confirm_missing_fields(self):
        response = self.client.post(
            '/api/auth/password/reset/confirm/',
            data=json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('token', response.json())
        self.assertIn('new_password1', response.json())

    def test_password_reset_confirm_password_mismatch(self):
        raw_token = secrets.token_urlsafe(32)
        user = User.objects.create_user(
            email='mismatch@example.com',
            username='mismatch',
            password='oldpassword123',
        )
        PasswordResetToken.objects.create(user=user, token=hashlib.sha256(raw_token.encode()).hexdigest())
        response = self.client.post(
            '/api/auth/password/reset/confirm/',
            data=json.dumps({
                'token': raw_token,
                'new_password1': 'newpassword456',
                'new_password2': 'different',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('new_password2', response.json())


# ---------------------------------------------------------------------------
# Category tests
# ---------------------------------------------------------------------------

class CategoryTests(BaseTestCase):
    def test_list_categories_public(self):
        response = self.client.get('/api/categories/')
        self.assertEqual(response.status_code, 200)
        slugs = [c['slug'] for c in response.json()]
        self.assertIn('worship', slugs)
        self.assertIn('youth', slugs)

    def test_list_categories_excludes_inactive(self):
        Category.objects.create(name='Hidden', slug='hidden', is_active=False)
        response = self.client.get('/api/categories/')
        slugs = [c['slug'] for c in response.json()]
        self.assertNotIn('hidden', slugs)

    def test_category_payload_fields(self):
        response = self.client.get('/api/categories/')
        category = response.json()[0]
        expected = {'id', 'name', 'slug', 'icon', 'description', 'events_count', 'is_active', 'sort_order'}
        self.assertEqual(set(category.keys()), expected)

    def test_create_category_admin(self):
        response = self.client.post(
            '/api/categories/',
            data=json.dumps({'name': 'Arts', 'slug': 'arts', 'icon': 'camera'}),
            content_type='application/json',
            **self.auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['slug'], 'arts')

    def test_create_category_non_admin_forbidden(self):
        token, _ = self.register()
        response = self.client.post(
            '/api/categories/',
            data=json.dumps({'name': 'Arts', 'slug': 'arts'}),
            content_type='application/json',
            **self.auth(token),
        )
        self.assertEqual(response.status_code, 403)

    def test_create_category_unauthenticated(self):
        response = self.client.post(
            '/api/categories/',
            data=json.dumps({'name': 'Arts', 'slug': 'arts'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)

    def test_create_category_duplicate_slug(self):
        response = self.client.post(
            '/api/categories/',
            data=json.dumps({'name': 'Worship 2', 'slug': 'worship'}),
            content_type='application/json',
            **self.auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('slug', response.json())

    def test_create_category_missing_name(self):
        response = self.client.post(
            '/api/categories/',
            data=json.dumps({'slug': 'noname'}),
            content_type='application/json',
            **self.auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('name', response.json())

    def test_create_category_auto_slug(self):
        response = self.client.post(
            '/api/categories/',
            data=json.dumps({'name': 'Music Ministry'}),
            content_type='application/json',
            **self.auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['slug'], 'music-ministry')

    def test_patch_category(self):
        response = self.client.post(
            '/api/categories/',
            data=json.dumps({'name': 'Test', 'slug': 'test'}),
            content_type='application/json',
            **self.auth(self.admin_token),
        )
        cat_id = response.json()['id']
        patch = self.client.patch(
            f'/api/categories/{cat_id}/',
            data=json.dumps({'sort_order': 99, 'icon': 'star'}),
            content_type='application/json',
            **self.auth(self.admin_token),
        )
        self.assertEqual(patch.status_code, 200)
        self.assertEqual(patch.json()['sort_order'], 99)
        self.assertEqual(patch.json()['icon'], 'star')

    def test_patch_category_duplicate_slug(self):
        cat = Category.objects.create(name='Test', slug='test')
        response = self.client.patch(
            f'/api/categories/{cat.id}/',
            data=json.dumps({'slug': 'worship'}),
            content_type='application/json',
            **self.auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('slug', response.json())

    def test_delete_category_soft_deletes(self):
        cat = Category.objects.create(name='ToDelete', slug='to-delete')
        response = self.client.delete(
            f'/api/categories/{cat.id}/',
            **self.auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['is_active'])
        cat.refresh_from_db()
        self.assertFalse(cat.is_active)

    def test_category_detail_not_found(self):
        response = self.client.patch(
            '/api/categories/9999/',
            data=json.dumps({'name': 'Nope'}),
            content_type='application/json',
            **self.auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# Event tests
# ---------------------------------------------------------------------------

class EventTests(BaseTestCase):
    def test_create_event_authenticated(self):
        token, _ = self.register()
        response = self.create_event(token)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['approval_status'], 'pending')
        self.assertEqual(response.json()['category']['slug'], 'worship')

    def test_create_event_unauthenticated(self):
        response = self.client.post(
            '/api/events/',
            data=json.dumps({
                'title': 'Test',
                'description': 'desc',
                'date': FUTURE_DATE,
                'location': 'Lagos',
                'pricing': 'free',
                'category': 'worship',
                'language': 'english',
                'age_group': 'all_ages',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)

    def test_create_event_missing_required_field(self):
        token, _ = self.register()
        response = self.create_event(token, title='')
        self.assertEqual(response.status_code, 400)
        self.assertIn('title', response.json())

    def test_create_event_invalid_category(self):
        token, _ = self.register()
        response = self.create_event(token, category='nonexistent')
        self.assertEqual(response.status_code, 400)
        self.assertIn('category', response.json())

    def test_create_event_inactive_category(self):
        Category.objects.create(name='Inactive', slug='inactive', is_active=False)
        token, _ = self.register()
        response = self.create_event(token, category='inactive')
        self.assertEqual(response.status_code, 400)
        self.assertIn('category', response.json())

    def test_create_event_paid_without_price(self):
        token, _ = self.register()
        response = self.create_event(token, pricing='paid', ticket_price=None)
        self.assertEqual(response.status_code, 400)
        self.assertIn('ticket_price', response.json())

    def test_create_event_paid_with_price(self):
        token, _ = self.register()
        response = self.create_event(token, pricing='paid', ticket_price='5000.00')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['ticket_price'], 5000.0)

    def test_create_event_free_strips_price(self):
        token, _ = self.register()
        response = self.create_event(token, pricing='free', ticket_price='1000.00')
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.json()['ticket_price'])

    def test_create_event_past_date_rejected(self):
        token, _ = self.register()
        response = self.create_event(token, date=PAST_DATE)
        self.assertEqual(response.status_code, 400)
        self.assertIn('date', response.json())

    def test_create_event_end_before_start(self):
        token, _ = self.register()
        response = self.create_event(
            token,
            date=FUTURE_END,
            end_date=FUTURE_DATE,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('end_date', response.json())

    def test_create_event_invalid_datetime(self):
        token, _ = self.register()
        response = self.create_event(token, date='not-a-date')
        self.assertEqual(response.status_code, 400)
        self.assertIn('date', response.json())

    def test_create_event_invalid_decimal(self):
        token, _ = self.register()
        response = self.create_event(token, location_lat='not-a-number')
        self.assertEqual(response.status_code, 400)
        self.assertIn('location_lat', response.json())

    def test_create_event_negative_capacity(self):
        token, _ = self.register()
        response = self.create_event(token, capacity=-5)
        self.assertEqual(response.status_code, 400)
        self.assertIn('capacity', response.json())

    def test_list_events_only_approved(self):
        token, _ = self.register()
        event = self.create_event(token).json()
        # Pending event should not appear in public list.
        response = self.client.get('/api/events/')
        self.assertEqual(response.json()['count'], 0)
        self.approve_event(event['id'])
        response = self.client.get('/api/events/')
        self.assertEqual(response.json()['count'], 1)

    def test_list_events_search(self):
        token, _ = self.register()
        e1 = self.create_event(token, title='Lagos Worship Night').json()
        e2 = self.create_event(token, title='Youth Conference').json()
        self.approve_event(e1['id'])
        self.approve_event(e2['id'])

        response = self.client.get('/api/events/?search=conference')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['title'], 'Youth Conference')

    def test_list_events_filter_by_category(self):
        token, _ = self.register()
        e1 = self.create_event(token, title='Worship Event').json()
        e2 = self.create_event(token, title='Youth Event', category='youth').json()
        self.approve_event(e1['id'])
        self.approve_event(e2['id'])

        response = self.client.get('/api/events/?category=youth')
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['title'], 'Youth Event')

    def test_list_events_filter_by_pricing(self):
        token, _ = self.register()
        e1 = self.create_event(token, title='Free Event').json()
        e2 = self.create_event(token, title='Paid Event', pricing='paid', ticket_price='1000.00').json()
        self.approve_event(e1['id'])
        self.approve_event(e2['id'])

        response = self.client.get('/api/events/?pricing=paid')
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['title'], 'Paid Event')

    def test_list_events_filter_by_language(self):
        token, _ = self.register()
        e1 = self.create_event(token, title='English Event').json()
        e2 = self.create_event(token, title='Yoruba Event', language='yoruba').json()
        self.approve_event(e1['id'])
        self.approve_event(e2['id'])

        response = self.client.get('/api/events/?language=yoruba')
        self.assertEqual(response.json()['count'], 1)

    def test_list_events_filter_featured(self):
        token, _ = self.register()
        e1 = self.create_event(token, title='Featured').json()
        e2 = self.create_event(token, title='Normal').json()
        self.approve_event(e1['id'])
        self.approve_event(e2['id'])
        # Mark e1 as featured via admin patch.
        self.client.patch(
            f'/api/events/{e1["id"]}/',
            data=json.dumps({'is_featured': True}),
            content_type='application/json',
            **self.auth(self.admin_token),
        )

        response = self.client.get('/api/events/?is_featured=true')
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['title'], 'Featured')

    def test_list_events_ordering(self):
        token, _ = self.register()
        e1 = self.create_event(token, title='A Event').json()
        e2 = self.create_event(token, title='B Event').json()
        self.approve_event(e1['id'])
        self.approve_event(e2['id'])

        response = self.client.get('/api/events/?ordering=title')
        titles = [r['title'] for r in response.json()['results']]
        self.assertEqual(titles, sorted(titles))

    def test_list_events_invalid_ordering_falls_back(self):
        token, _ = self.register()
        e = self.create_event(token).json()
        self.approve_event(e['id'])
        response = self.client.get('/api/events/?ordering=invalid_field')
        self.assertEqual(response.status_code, 200)

    def test_list_events_pagination(self):
        token, _ = self.register()
        for i in range(5):
            e = self.create_event(token, title=f'Event {i}').json()
            self.approve_event(e['id'])

        response = self.client.get('/api/events/?page_size=2&page=1')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['count'], 5)
        self.assertEqual(len(body['results']), 2)
        self.assertIsNotNone(body['next'])
        self.assertIsNone(body['previous'])

    def test_event_detail_get_approved_public(self):
        token, _ = self.register()
        e = self.create_event(token).json()
        self.approve_event(e['id'])
        response = self.client.get(f'/api/events/{e["id"]}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['title'], 'Sunday Worship')

    def test_event_detail_pending_not_visible_to_public(self):
        token, _ = self.register()
        e = self.create_event(token).json()
        self.clear_auth()
        response = self.client.get(f'/api/events/{e["id"]}/')
        self.assertEqual(response.status_code, 404)

    def test_event_detail_pending_visible_to_creator(self):
        token, _ = self.register()
        e = self.create_event(token).json()
        response = self.client.get(f'/api/events/{e["id"]}/', **self.auth(token))
        self.assertEqual(response.status_code, 200)

    def test_event_detail_pending_visible_to_admin(self):
        token, _ = self.register()
        e = self.create_event(token).json()
        response = self.client.get(f'/api/events/{e["id"]}/', **self.auth(self.admin_token))
        self.assertEqual(response.status_code, 200)

    def test_event_detail_not_found(self):
        response = self.client.get('/api/events/9999/')
        self.assertEqual(response.status_code, 404)

    def test_event_patch_by_creator(self):
        token, _ = self.register()
        e = self.create_event(token).json()
        response = self.client.patch(
            f'/api/events/{e["id"]}/',
            data=json.dumps({'title': 'Updated Title'}),
            content_type='application/json',
            **self.auth(token),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['title'], 'Updated Title')

    def test_event_patch_by_non_creator_forbidden(self):
        token, _ = self.register()
        token2, _ = self.register(email='other@example.com', username='other')
        e = self.create_event(token).json()
        self.approve_event(e['id'])
        response = self.client.patch(
            f'/api/events/{e["id"]}/',
            data=json.dumps({'title': 'Hacked'}),
            content_type='application/json',
            **self.auth(token2),
        )
        self.assertEqual(response.status_code, 403)

    def test_event_patch_unauthenticated(self):
        token, _ = self.register()
        e = self.create_event(token).json()
        self.approve_event(e['id'])
        self.clear_auth()
        response = self.client.patch(
            f'/api/events/{e["id"]}/',
            data=json.dumps({'title': 'Hacked'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)

    def test_event_delete_by_creator(self):
        token, _ = self.register()
        e = self.create_event(token).json()
        response = self.client.delete(f'/api/events/{e["id"]}/', **self.auth(token))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.filter(id=e['id']).exists())

    def test_event_delete_by_non_creator_forbidden(self):
        token, _ = self.register()
        token2, _ = self.register(email='other@example.com', username='other')
        e = self.create_event(token).json()
        self.approve_event(e['id'])
        response = self.client.delete(f'/api/events/{e["id"]}/', **self.auth(token2))
        self.assertEqual(response.status_code, 403)

    def test_admin_approve_event_sends_notification(self):
        token, _ = self.register()
        e = self.create_event(token).json()
        self.approve_event(e['id'])
        notif = Notification.objects.filter(
            user__email='user@example.com',
            type='event_approved',
        ).first()
        self.assertIsNotNone(notif)

    def test_admin_reject_event_sends_notification(self):
        token, _ = self.register()
        e = self.create_event(token).json()
        self.client.patch(
            f'/api/events/{e["id"]}/',
            data=json.dumps({'approval_status': 'rejected', 'rejection_reason': 'Bad venue'}),
            content_type='application/json',
            **self.auth(self.admin_token),
        )
        notif = Notification.objects.filter(
            user__email='user@example.com',
            type='event_rejected',
        ).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.detail, 'Bad venue')

    def test_admin_invalid_approval_status(self):
        token, _ = self.register()
        e = self.create_event(token).json()
        response = self.client.patch(
            f'/api/events/{e["id"]}/',
            data=json.dumps({'approval_status': 'bogus'}),
            content_type='application/json',
            **self.auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('approval_status', response.json())

    def test_related_events(self):
        token, _ = self.register()
        e1 = self.create_event(token, title='Event A').json()
        e2 = self.create_event(token, title='Event B').json()
        self.approve_event(e1['id'])
        self.approve_event(e2['id'])

        response = self.client.get(f'/api/events/{e1["id"]}/related/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['title'], 'Event B')

    def test_related_events_excludes_self(self):
        token, _ = self.register()
        e = self.create_event(token).json()
        self.approve_event(e['id'])
        response = self.client.get(f'/api/events/{e["id"]}/related/')
        related_ids = [r['id'] for r in response.json()['results']]
        self.assertNotIn(e['id'], related_ids)

    def test_event_payload_includes_engagement_flags(self):
        token, _ = self.register()
        e = self.create_event(token).json()
        self.approve_event(e['id'])
        # Like and RSVP.
        self.client.post(f'/api/events/{e["id"]}/like/', **self.auth(token))
        self.client.post(f'/api/events/{e["id"]}/rsvp/', **self.auth(token))

        response = self.client.get(f'/api/events/{e["id"]}/', **self.auth(token))
        body = response.json()
        self.assertTrue(body['is_liked'])
        self.assertTrue(body['is_rsvped'])
        self.assertFalse(body['is_saved'])
        self.assertEqual(body['likes_count'], 1)
        self.assertEqual(body['rsvp_count'], 1)


# ---------------------------------------------------------------------------
# Like / Save / RSVP tests
# ---------------------------------------------------------------------------

class EngagementTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.token, self.user = self.register()
        self.event = self.create_event(self.token).json()
        self.approve_event(self.event['id'])

    def test_like_creates_like(self):
        response = self.client.post(f'/api/events/{self.event["id"]}/like/', **self.auth(self.token))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['liked'])
        self.assertEqual(response.json()['likes_count'], 1)

    def test_like_toggle_removes_like(self):
        self.client.post(f'/api/events/{self.event["id"]}/like/', **self.auth(self.token))
        response = self.client.post(f'/api/events/{self.event["id"]}/like/', **self.auth(self.token))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['liked'])
        self.assertEqual(response.json()['likes_count'], 0)

    def test_like_unauthenticated(self):
        self.clear_auth()
        response = self.client.post(f'/api/events/{self.event["id"]}/like/')
        self.assertEqual(response.status_code, 401)

    def test_like_nonexistent_event(self):
        response = self.client.post('/api/events/9999/like/', **self.auth(self.token))
        self.assertEqual(response.status_code, 404)

    def test_save_creates_save(self):
        response = self.client.post(f'/api/events/{self.event["id"]}/save/', **self.auth(self.token))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['saved'])
        self.assertEqual(response.json()['saves_count'], 1)

    def test_save_toggle_removes_save(self):
        self.client.post(f'/api/events/{self.event["id"]}/save/', **self.auth(self.token))
        response = self.client.post(f'/api/events/{self.event["id"]}/save/', **self.auth(self.token))
        self.assertFalse(response.json()['saved'])
        self.assertEqual(response.json()['saves_count'], 0)

    def test_save_unauthenticated(self):
        self.clear_auth()
        response = self.client.post(f'/api/events/{self.event["id"]}/save/')
        self.assertEqual(response.status_code, 401)

    def test_rsvp_creates_rsvp(self):
        response = self.client.post(f'/api/events/{self.event["id"]}/rsvp/', **self.auth(self.token))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['rsvped'])
        self.assertEqual(response.json()['rsvp_count'], 1)

    def test_rsvp_toggle_removes_rsvp(self):
        self.client.post(f'/api/events/{self.event["id"]}/rsvp/', **self.auth(self.token))
        response = self.client.post(f'/api/events/{self.event["id"]}/rsvp/', **self.auth(self.token))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['rsvped'])
        self.assertEqual(response.json()['rsvp_count'], 0)

    def test_rsvp_unauthenticated(self):
        self.clear_auth()
        response = self.client.post(f'/api/events/{self.event["id"]}/rsvp/')
        self.assertEqual(response.status_code, 401)

    def test_rsvp_full_capacity(self):
        # Create event with capacity 1.
        e = self.create_event(self.token, title='Small Event', capacity=1).json()
        self.approve_event(e['id'])
        token2, _ = self.register(email='other@example.com', username='other')
        self.client.post(f'/api/events/{e["id"]}/rsvp/', **self.auth(self.token))
        response = self.client.post(f'/api/events/{e["id"]}/rsvp/', **self.auth(token2))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['detail'], 'This event is at full capacity.')

    def test_rsvp_creates_notification(self):
        self.client.post(f'/api/events/{self.event["id"]}/rsvp/', **self.auth(self.token))
        notif = Notification.objects.filter(
            user__email='user@example.com',
            type='rsvp_confirmed',
        ).first()
        self.assertIsNotNone(notif)

    def test_rsvp_on_pending_event_by_non_creator(self):
        e = self.create_event(self.token, title='Pending').json()
        token2, _ = self.register(email='other@example.com', username='other')
        response = self.client.post(f'/api/events/{e["id"]}/rsvp/', **self.auth(token2))
        self.assertEqual(response.status_code, 404)

    def test_event_attendees_by_creator(self):
        self.client.post(f'/api/events/{self.event["id"]}/rsvp/', **self.auth(self.token))
        response = self.client.get(f'/api/events/{self.event["id"]}/attendees/', **self.auth(self.token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['email'], 'user@example.com')

    def test_event_attendees_by_non_creator_forbidden(self):
        token2, _ = self.register(email='other@example.com', username='other')
        response = self.client.get(f'/api/events/{self.event["id"]}/attendees/', **self.auth(token2))
        self.assertEqual(response.status_code, 403)

    def test_event_attendees_unauthenticated(self):
        self.clear_auth()
        response = self.client.get(f'/api/events/{self.event["id"]}/attendees/')
        self.assertEqual(response.status_code, 401)

    def test_event_attendees_not_found(self):
        response = self.client.get('/api/events/9999/attendees/', **self.auth(self.token))
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# Event collection list tests (liked, saved, my, attending)
# ---------------------------------------------------------------------------

class EventListTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.token, self.user = self.register()
        self.event = self.create_event(self.token).json()
        self.approve_event(self.event['id'])

    # Personal collections are flat arrays: the frontend consumes them as Event[].
    def test_liked_events_list(self):
        self.client.post(f'/api/events/{self.event["id"]}/like/', **self.auth(self.token))
        response = self.client.get('/api/events/liked/', **self.auth(self.token))
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
        self.assertEqual(len(response.json()), 1)

    def test_saved_events_list(self):
        self.client.post(f'/api/events/{self.event["id"]}/save/', **self.auth(self.token))
        response = self.client.get('/api/events/saved/', **self.auth(self.token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_my_events_includes_all_statuses(self):
        self.create_event(self.token, title='Second Event')
        # Do not approve e2; my_events should still show it.
        response = self.client.get('/api/events/my-events/', **self.auth(self.token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)

    def test_attending_events(self):
        self.client.post(f'/api/events/{self.event["id"]}/rsvp/', **self.auth(self.token))
        response = self.client.get('/api/events/attending/', **self.auth(self.token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_liked_events_unauthenticated(self):
        self.clear_auth()
        response = self.client.get('/api/events/liked/')
        self.assertEqual(response.status_code, 401)

    def test_saved_events_unauthenticated(self):
        self.clear_auth()
        response = self.client.get('/api/events/saved/')
        self.assertEqual(response.status_code, 401)

    def test_my_events_unauthenticated(self):
        self.clear_auth()
        response = self.client.get('/api/events/my-events/')
        self.assertEqual(response.status_code, 401)

    def test_attending_events_unauthenticated(self):
        self.clear_auth()
        response = self.client.get('/api/events/attending/')
        self.assertEqual(response.status_code, 401)


# ---------------------------------------------------------------------------
# Public user tests
# ---------------------------------------------------------------------------

class PublicUserTests(BaseTestCase):
    def test_public_user_profile(self):
        token, user = self.register()
        e = self.create_event(token).json()
        self.approve_event(e['id'])
        response = self.client.get(f'/api/users/{user["id"]}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['first_name'], 'John')
        self.assertEqual(response.json()['events_created_count'], 1)

    def test_public_user_not_found(self):
        response = self.client.get('/api/users/9999/')
        self.assertEqual(response.status_code, 404)

    def test_public_user_events(self):
        token, user = self.register()
        e = self.create_event(token).json()
        self.approve_event(e['id'])
        response = self.client.get(f'/api/users/{user["id"]}/events/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)

    def test_public_user_events_not_found(self):
        response = self.client.get('/api/users/9999/events/')
        self.assertEqual(response.status_code, 404)

    def test_public_user_events_only_approved(self):
        token, user = self.register()
        self.create_event(token).json()  # stays pending
        response = self.client.get(f'/api/users/{user["id"]}/events/')
        self.assertEqual(response.json()['count'], 0)


# ---------------------------------------------------------------------------
# Notification tests
# ---------------------------------------------------------------------------

class NotificationTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.token, self.user = self.register()
        self.event = self.create_event(self.token).json()
        self.approve_event(self.event['id'])

    def test_list_notifications(self):
        # RSVP to generate a notification.
        self.client.post(f'/api/events/{self.event["id"]}/rsvp/', **self.auth(self.token))
        response = self.client.get('/api/notifications/', **self.auth(self.token))
        self.assertEqual(response.status_code, 200)
        self.assertIn('count', response.json())
        self.assertGreater(response.json()['count'], 0)

    def test_list_notifications_unauthenticated(self):
        self.clear_auth()
        response = self.client.get('/api/notifications/')
        self.assertEqual(response.status_code, 401)

    def test_list_notifications_filter_unread(self):
        self.client.post(f'/api/events/{self.event["id"]}/rsvp/', **self.auth(self.token))
        self.client.post('/api/notifications/read-all/', **self.auth(self.token))
        response = self.client.get('/api/notifications/?is_read=false', **self.auth(self.token))
        self.assertEqual(response.json()['count'], 0)

    def test_list_notifications_filter_read(self):
        self.client.post(f'/api/events/{self.event["id"]}/rsvp/', **self.auth(self.token))
        self.client.post('/api/notifications/read-all/', **self.auth(self.token))
        response = self.client.get('/api/notifications/?is_read=true', **self.auth(self.token))
        self.assertGreater(response.json()['count'], 0)

    def test_unread_count(self):
        self.client.post(f'/api/events/{self.event["id"]}/rsvp/', **self.auth(self.token))
        response = self.client.get('/api/notifications/unread-count/', **self.auth(self.token))
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.json()['count'], 0)

    def test_mark_notification_read(self):
        self.client.post(f'/api/events/{self.event["id"]}/rsvp/', **self.auth(self.token))
        notif_id = self.client.get('/api/notifications/', **self.auth(self.token)).json()['results'][0]['id']
        response = self.client.post(f'/api/notifications/{notif_id}/read/', **self.auth(self.token))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['is_read'])

    def test_mark_notification_read_not_found(self):
        response = self.client.post('/api/notifications/9999/read/', **self.auth(self.token))
        self.assertEqual(response.status_code, 404)

    def test_mark_all_read(self):
        self.client.post(f'/api/events/{self.event["id"]}/rsvp/', **self.auth(self.token))
        response = self.client.post('/api/notifications/read-all/', **self.auth(self.token))
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.json()['updated'], 0)

    def test_delete_notification(self):
        self.client.post(f'/api/events/{self.event["id"]}/rsvp/', **self.auth(self.token))
        notif_id = self.client.get('/api/notifications/', **self.auth(self.token)).json()['results'][0]['id']
        response = self.client.delete(f'/api/notifications/{notif_id}/', **self.auth(self.token))
        self.assertEqual(response.status_code, 204)

    def test_delete_notification_not_found(self):
        response = self.client.delete('/api/notifications/9999/', **self.auth(self.token))
        self.assertEqual(response.status_code, 404)

    def test_notifications_only_own_user(self):
        # Create notification for admin.
        Notification.objects.create(
            user=self.admin,
            type='reminder',
            title='Admin notif',
            body='Private',
        )
        # User should not see admin's notifications.
        response = self.client.get('/api/notifications/', **self.auth(self.token))
        notif_bodies = [n['body'] for n in response.json()['results']]
        self.assertNotIn('Private', notif_bodies)


# ---------------------------------------------------------------------------
# Image upload tests
# ---------------------------------------------------------------------------

class ImageUploadTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.token, self.user = self.register()

    def _event_data(self, **overrides):
        data = {
            'title': 'Image Event',
            'description': 'With image',
            'date': FUTURE_DATE,
            'location': 'Lagos',
            'pricing': 'free',
            'category': 'worship',
            'language': 'english',
            'age_group': 'all_ages',
        }
        data.update(overrides)
        return data

    def test_upload_valid_image(self):
        img = make_image_file(size=(200, 200))
        response = self.client.post(
            '/api/events/',
            data={**self._event_data(), 'image': img},
            **self.auth(self.token),
        )
        self.assertEqual(response.status_code, 201)
        self.assertIsNotNone(response.json()['image'])

    def test_upload_invalid_content_type(self):
        bad_file = SimpleUploadedFile('test.txt', b'not an image', content_type='text/plain')
        response = self.client.post(
            '/api/events/',
            data={**self._event_data(title='Bad Type'), 'image': bad_file},
            **self.auth(self.token),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('image', response.json())

    def test_upload_corrupt_image(self):
        bad_file = SimpleUploadedFile('test.jpg', b'not an image at all', content_type='image/jpeg')
        response = self.client.post(
            '/api/events/',
            data={**self._event_data(title='Corrupt'), 'image': bad_file},
            **self.auth(self.token),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('image', response.json())


# ---------------------------------------------------------------------------
# Health check and error handler tests
# ---------------------------------------------------------------------------

class HealthAndErrorTests(BaseTestCase):
    def test_health_check(self):
        response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')

    def test_unknown_api_route_returns_json_404(self):
        response = self.client.get('/api/nope/')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {'detail': 'Not found.'})

    def test_method_not_allowed(self):
        response = self.client.put('/api/auth/register/')
        self.assertEqual(response.status_code, 405)


# ---------------------------------------------------------------------------
# Model validation tests
# ---------------------------------------------------------------------------

class ModelValidationTests(BaseTestCase):
    def test_event_clean_end_before_start(self):
        from django.core.exceptions import ValidationError
        cat = Category.objects.first()
        event = Event(
            title='Test',
            description='desc',
            date=timezone.now() + timedelta(days=2),
            end_date=timezone.now() + timedelta(days=1),
            location='Lagos',
            pricing='free',
            category=cat,
            language='english',
            age_group='all_ages',
            created_by=self.admin,
        )
        with self.assertRaises(ValidationError):
            event.clean()

    def test_event_clean_paid_requires_price(self):
        from django.core.exceptions import ValidationError
        cat = Category.objects.first()
        event = Event(
            title='Test',
            description='desc',
            date=timezone.now() + timedelta(days=2),
            location='Lagos',
            pricing='paid',
            ticket_price=None,
            category=cat,
            language='english',
            age_group='all_ages',
            created_by=self.admin,
        )
        with self.assertRaises(ValidationError):
            event.clean()

    def test_event_clean_free_strips_price(self):
        cat = Category.objects.first()
        event = Event(
            title='Test',
            description='desc',
            date=timezone.now() + timedelta(days=2),
            location='Lagos',
            pricing='free',
            ticket_price=100,
            category=cat,
            language='english',
            age_group='all_ages',
            created_by=self.admin,
        )
        event.clean()
        self.assertIsNone(event.ticket_price)

    def test_unique_event_like(self):
        from django.db import IntegrityError
        token, _ = self.register()
        e = self.create_event(token).json()
        self.approve_event(e['id'])
        user = User.objects.get(email='user@example.com')
        event = Event.objects.get(id=e['id'])
        EventLike.objects.create(user=user, event=event)
        with self.assertRaises(IntegrityError):
            EventLike.objects.create(user=user, event=event)

    def test_unique_event_save(self):
        from django.db import IntegrityError
        token, _ = self.register()
        e = self.create_event(token).json()
        self.approve_event(e['id'])
        user = User.objects.get(email='user@example.com')
        event = Event.objects.get(id=e['id'])
        EventSave.objects.create(user=user, event=event)
        with self.assertRaises(IntegrityError):
            EventSave.objects.create(user=user, event=event)

    def test_unique_rsvp(self):
        from django.db import IntegrityError
        token, _ = self.register()
        e = self.create_event(token).json()
        self.approve_event(e['id'])
        user = User.objects.get(email='user@example.com')
        event = Event.objects.get(id=e['id'])
        RSVP.objects.create(user=user, event=event)
        with self.assertRaises(IntegrityError):
            RSVP.objects.create(user=user, event=event)

    def test_event_is_full_property(self):
        token, _ = self.register()
        e = self.create_event(self.token if hasattr(self, 'token') else token, capacity=1).json()
        self.approve_event(e['id'])
        user = User.objects.get(email='user@example.com')
        event = Event.objects.get(id=e['id'])
        self.assertFalse(event.is_full)
        RSVP.objects.create(user=user, event=event)
        event.refresh_from_db()
        self.assertTrue(event.is_full)

    def test_event_rsvp_count_property(self):
        token, _ = self.register()
        e = self.create_event(token).json()
        self.approve_event(e['id'])
        event = Event.objects.get(id=e['id'])
        self.assertEqual(event.rsvp_count, 0)
        RSVP.objects.create(user=User.objects.get(email='user@example.com'), event=event)
        self.assertEqual(event.rsvp_count, 1)


# ---------------------------------------------------------------------------
# Services tests
# ---------------------------------------------------------------------------

class ServicesTests(BaseTestCase):
    def test_notify_event_approved_creates_notification(self):
        from .services import notify_event_approved
        token, _ = self.register()
        e = self.create_event(token).json()
        event = Event.objects.get(id=e['id'])
        notify_event_approved(event)
        notif = Notification.objects.filter(user=event.created_by, type='event_approved').first()
        self.assertIsNotNone(notif)

    def test_notify_event_rejected_creates_notification(self):
        from .services import notify_event_rejected
        token, _ = self.register()
        e = self.create_event(token).json()
        event = Event.objects.get(id=e['id'])
        event.rejection_reason = 'Nope'
        notify_event_rejected(event)
        notif = Notification.objects.filter(user=event.created_by, type='event_rejected').first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.detail, 'Nope')

    def test_notify_event_cancelled_creates_notifications_for_attendees(self):
        from .services import notify_event_cancelled
        token, _ = self.register()
        e = self.create_event(token).json()
        self.approve_event(e['id'])
        event = Event.objects.get(id=e['id'])
        user = User.objects.get(email='user@example.com')
        RSVP.objects.create(user=user, event=event)
        notify_event_cancelled(event)
        notif = Notification.objects.filter(user=user, type='event_cancelled').first()
        self.assertIsNotNone(notif)

    def test_notify_rsvp_confirmed_creates_notification(self):
        from .services import notify_rsvp_confirmed
        token, _ = self.register()
        e = self.create_event(token).json()
        self.approve_event(e['id'])
        event = Event.objects.get(id=e['id'])
        user = User.objects.get(email='user@example.com')
        notify_rsvp_confirmed(user, event)
        notif = Notification.objects.filter(user=user, type='rsvp_confirmed').first()
        self.assertIsNotNone(notif)

    def test_notify_event_status_change_approved(self):
        from .services import notify_event_status_change
        token, _ = self.register()
        e = self.create_event(token).json()
        event = Event.objects.get(id=e['id'])
        event.approval_status = 'approved'
        notify_event_status_change(event)
        notif = Notification.objects.filter(user=event.created_by, type='event_approved').first()
        self.assertIsNotNone(notif)

    def test_notify_event_status_change_rejected(self):
        from .services import notify_event_status_change
        token, _ = self.register()
        e = self.create_event(token).json()
        event = Event.objects.get(id=e['id'])
        event.approval_status = 'rejected'
        event.rejection_reason = 'Bad'
        notify_event_status_change(event)
        notif = Notification.objects.filter(user=event.created_by, type='event_rejected').first()
        self.assertIsNotNone(notif)
