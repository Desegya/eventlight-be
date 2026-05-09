import json

from django.test import Client, TestCase


class ApiContractTests(TestCase):
    def setUp(self):
        self.client = Client()

    def register(self):
        response = self.client.post(
            '/api/auth/register/',
            data=json.dumps(
                {
                    'email': 'user@example.com',
                    'password': 'password123',
                    'first_name': 'John',
                    'last_name': 'Doe',
                    'username': 'johndoe',
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        return response.json()['key']

    def test_auth_profile_event_and_toggle_flow(self):
        token = self.register()
        auth = {'HTTP_AUTHORIZATION': f'Token {token}'}

        user_response = self.client.get('/api/auth/user/', **auth)
        self.assertEqual(user_response.status_code, 200)
        self.assertEqual(user_response.json()['country'], 'Nigeria')

        categories_response = self.client.get('/api/categories/')
        self.assertEqual(categories_response.status_code, 200)
        self.assertEqual(categories_response.json()[0].keys(), {'id', 'name', 'slug', 'description', 'is_active'})

        update_response = self.client.patch(
            '/api/auth/user/',
            data=json.dumps({'city': 'Lagos', 'preferred_categories': ['worship']}),
            content_type='application/json',
            **auth,
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()['city'], 'Lagos')

        create_response = self.client.post(
            '/api/events/',
            data=json.dumps(
                {
                    'title': 'Sunday Worship',
                    'description': 'Join us.',
                    'organizer': 'Lagos Christian Center',
                    'date': '2026-06-01T10:00:00Z',
                    'location': 'Lagos',
                    'pricing': 'free',
                    'category': 'worship',
                    'event_type': 'church_service',
                    'language': 'english',
                    'age_group': 'all_ages',
                }
            ),
            content_type='application/json',
            **auth,
        )
        self.assertEqual(create_response.status_code, 201)
        event = create_response.json()
        self.assertEqual(event['organizer'], 'Lagos Christian Center')
        self.assertEqual(event['likes_count'], 0)

        second_create_response = self.client.post(
            '/api/events/',
            data=json.dumps(
                {
                    'title': 'Youth Conference',
                    'description': 'Leadership gathering.',
                    'organizer': 'Youth Network',
                    'date': '2026-07-01T10:00:00Z',
                    'location': 'Abuja',
                    'pricing': 'paid',
                    'category': 'youth',
                    'event_type': 'conference',
                    'language': 'english',
                    'age_group': 'young_adults',
                }
            ),
            content_type='application/json',
            **auth,
        )
        self.assertEqual(second_create_response.status_code, 201)

        list_response = self.client.get('/api/events/')
        self.assertEqual(list_response.status_code, 200)
        event_list = list_response.json()
        self.assertEqual(event_list['count'], 2)
        self.assertIsNone(event_list['next'])
        self.assertIsNone(event_list['previous'])
        self.assertIsInstance(event_list['results'], list)

        search_response = self.client.get('/api/events/?search=conference&pricing=paid')
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.json()['count'], 1)
        self.assertEqual(search_response.json()['results'][0]['title'], 'Youth Conference')

        paged_response = self.client.get('/api/events/?page_size=1')
        self.assertEqual(paged_response.status_code, 200)
        self.assertEqual(paged_response.json()['count'], 2)
        self.assertIsNotNone(paged_response.json()['next'])
        self.assertIsNone(paged_response.json()['previous'])
        self.assertEqual(len(paged_response.json()['results']), 1)

        category_response = self.client.get('/api/events/?category=worship&ordering=-date&page_size=1')
        self.assertEqual(category_response.status_code, 200)
        self.assertEqual(category_response.json()['count'], 1)
        self.assertEqual(category_response.json()['results'][0]['category'], 'worship')

        like_response = self.client.post(f'/api/events/{event["id"]}/like/', **auth)
        self.assertEqual(like_response.status_code, 200)
        self.assertEqual(like_response.json()['liked'], True)

        save_response = self.client.post(f'/api/events/{event["id"]}/save/', **auth)
        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(save_response.json()['saved'], True)

        liked_response = self.client.get('/api/events/liked/', **auth)
        self.assertEqual(liked_response.status_code, 200)
        self.assertEqual(len(liked_response.json()), 1)

        delete_response = self.client.delete(f'/api/events/{event["id"]}/', **auth)
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()['detail'], 'Event deleted successfully.')

        logout_response = self.client.post('/api/auth/logout/', **auth)
        self.assertEqual(logout_response.status_code, 200)
        self.assertEqual(logout_response.json()['detail'], 'Logged out successfully.')
