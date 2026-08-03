import json

from django.test import Client, TestCase
from knox.models import AuthToken

from .models import User


class ApiContractTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            email='admin@example.com',
            username='admin',
            password='password123',
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
                    'password': 'password123',
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
        return body['key'], body['user']

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
            data=json.dumps({'email': 'user@example.com', 'password': 'password123'}),
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
