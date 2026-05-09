from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from api.models import Category, Event, EventLike, EventSave, Notification, RSVP, User


CATEGORIES = (
    ('Worship', 'worship', 'heart', 'Worship and praise gatherings', 1),
    ('Music', 'music', 'music', 'Music concerts and worship music events', 2),
    ('Conference', 'conference', 'mic', 'Conferences and summits', 3),
    ('Seminar', 'seminar', 'book', 'Seminars and focused learning sessions', 4),
    ('Fellowship', 'fellowship', 'users', 'Fellowship and community gatherings', 5),
    ('Prayer', 'prayer', 'sun', 'Prayer meetings and vigils', 6),
    ('Youth', 'youth', 'award', 'Youth-focused events', 7),
    ('Outreach', 'outreach', 'message', 'Outreach and evangelism events', 8),
    ('Teaching', 'teaching', 'book', 'Teaching and discipleship events', 9),
    ('Children', 'children', 'star', 'Children and family events', 10),
)

USERS = (
    {
        'email': 'demo.organizer@eventlight.test',
        'username': 'demo_organizer',
        'first_name': 'Desmond',
        'last_name': 'Egya',
        'city': 'Lagos',
        'preferred_categories': ['worship', 'conference', 'teaching'],
    },
    {
        'email': 'ada@eventlight.test',
        'username': 'ada_obi',
        'first_name': 'Ada',
        'last_name': 'Obi',
        'city': 'Lagos',
        'preferred_categories': ['music', 'fellowship', 'prayer'],
    },
    {
        'email': 'tunde@eventlight.test',
        'username': 'tunde_balogun',
        'first_name': 'Tunde',
        'last_name': 'Balogun',
        'city': 'Ibadan',
        'preferred_categories': ['youth', 'outreach'],
    },
    {
        'email': 'mary@eventlight.test',
        'username': 'mary_okafor',
        'first_name': 'Mary',
        'last_name': 'Okafor',
        'city': 'Abuja',
        'preferred_categories': ['children', 'teaching'],
    },
)

EVENTS = (
    {
        'title': 'Sunday Night Worship',
        'category': 'worship',
        'days': 4,
        'duration_hours': 3,
        'location': 'Faith Tabernacle, Ota',
        'lat': '6.673100',
        'lng': '3.219600',
        'pricing': 'free',
        'language': 'english',
        'age_group': 'all_ages',
        'capacity': 800,
        'status': 'approved',
        'featured': True,
    },
    {
        'title': 'Lagos Youth Fire Conference',
        'category': 'youth',
        'days': 8,
        'duration_hours': 6,
        'location': 'National Stadium, Surulere, Lagos',
        'lat': '6.497400',
        'lng': '3.364300',
        'pricing': 'paid',
        'ticket_price': '5000.00',
        'language': 'english',
        'age_group': 'young_adults',
        'capacity': 500,
        'status': 'approved',
        'featured': True,
    },
    {
        'title': 'Morning Prayer Watch',
        'category': 'prayer',
        'days': 2,
        'duration_hours': 2,
        'location': 'House on the Rock, Lekki',
        'lat': '6.447400',
        'lng': '3.472300',
        'pricing': 'free',
        'language': 'english',
        'age_group': 'adults',
        'capacity': 120,
        'status': 'approved',
        'featured': False,
    },
    {
        'title': 'Kingdom Leadership Summit',
        'category': 'conference',
        'days': 14,
        'duration_hours': 8,
        'location': 'Eko Convention Centre, Lagos',
        'lat': '6.426500',
        'lng': '3.430900',
        'pricing': 'paid',
        'ticket_price': '15000.00',
        'language': 'english',
        'age_group': 'adults',
        'capacity': 1000,
        'status': 'approved',
        'featured': True,
    },
    {
        'title': 'Bible Teaching Intensive',
        'category': 'teaching',
        'days': 18,
        'duration_hours': 4,
        'location': 'The Elevation Church, Lagos',
        'lat': '6.436100',
        'lng': '3.461200',
        'pricing': 'free',
        'language': 'english',
        'age_group': 'all_ages',
        'capacity': 250,
        'status': 'approved',
        'featured': False,
    },
    {
        'title': 'Children Bible Fun Day',
        'category': 'children',
        'days': 21,
        'duration_hours': 5,
        'location': 'City Kids Centre, Abuja',
        'lat': '9.076500',
        'lng': '7.398600',
        'pricing': 'free',
        'language': 'english',
        'age_group': 'children',
        'capacity': 150,
        'status': 'approved',
        'featured': False,
    },
    {
        'title': 'Community Outreach Weekend',
        'category': 'outreach',
        'days': 11,
        'duration_hours': 7,
        'location': 'Ajegunle Community Hall, Lagos',
        'lat': '6.455200',
        'lng': '3.334100',
        'pricing': 'free',
        'language': 'pidgin',
        'age_group': 'all_ages',
        'capacity': 300,
        'status': 'approved',
        'featured': False,
    },
    {
        'title': 'Acoustic Worship Night',
        'category': 'music',
        'days': 6,
        'duration_hours': 3,
        'location': 'Freedom Park, Lagos Island',
        'lat': '6.449800',
        'lng': '3.396400',
        'pricing': 'paid',
        'ticket_price': '3000.00',
        'language': 'english',
        'age_group': 'young_adults',
        'capacity': 200,
        'status': 'approved',
        'featured': True,
    },
    {
        'title': 'Small Group Fellowship Dinner',
        'category': 'fellowship',
        'days': 9,
        'duration_hours': 3,
        'location': 'Maryland, Lagos',
        'lat': '6.572000',
        'lng': '3.367000',
        'pricing': 'free',
        'language': 'english',
        'age_group': 'adults',
        'capacity': 40,
        'status': 'approved',
        'featured': False,
    },
    {
        'title': 'Digital Ministry Seminar',
        'category': 'seminar',
        'days': 16,
        'duration_hours': 5,
        'location': 'Civic Centre, Victoria Island',
        'lat': '6.431900',
        'lng': '3.421900',
        'pricing': 'paid',
        'ticket_price': '7500.00',
        'language': 'english',
        'age_group': 'adults',
        'capacity': 180,
        'status': 'approved',
        'featured': False,
    },
    {
        'title': 'Yoruba Praise Evening',
        'category': 'music',
        'days': 24,
        'duration_hours': 4,
        'location': 'Ibadan Civic Centre',
        'lat': '7.377500',
        'lng': '3.947000',
        'pricing': 'free',
        'language': 'yoruba',
        'age_group': 'all_ages',
        'capacity': 350,
        'status': 'approved',
        'featured': False,
    },
    {
        'title': 'Igbo Family Thanksgiving',
        'category': 'fellowship',
        'days': 27,
        'duration_hours': 4,
        'location': 'Enugu Worship Centre',
        'lat': '6.524400',
        'lng': '7.518200',
        'pricing': 'free',
        'language': 'igbo',
        'age_group': 'all_ages',
        'capacity': 220,
        'status': 'approved',
        'featured': False,
    },
    {
        'title': 'Volunteer Training Bootcamp',
        'category': 'outreach',
        'days': 30,
        'duration_hours': 6,
        'location': 'Mainland Community Centre, Lagos',
        'lat': '6.601800',
        'lng': '3.351500',
        'pricing': 'free',
        'language': 'english',
        'age_group': 'young_adults',
        'capacity': 90,
        'status': 'pending',
        'featured': False,
    },
    {
        'title': 'Senior Saints Brunch',
        'category': 'fellowship',
        'days': 33,
        'duration_hours': 3,
        'location': 'GRA, Ikeja',
        'lat': '6.596200',
        'lng': '3.351900',
        'pricing': 'paid',
        'ticket_price': '2500.00',
        'language': 'english',
        'age_group': 'seniors',
        'capacity': 80,
        'status': 'pending',
        'featured': False,
    },
    {
        'title': 'Rejected Demo Event',
        'category': 'seminar',
        'days': 36,
        'duration_hours': 2,
        'location': 'Unknown Venue, Lagos',
        'lat': '6.524400',
        'lng': '3.379200',
        'pricing': 'free',
        'language': 'english',
        'age_group': 'adults',
        'capacity': 50,
        'status': 'rejected',
        'featured': False,
        'rejection_reason': 'Venue details need to be confirmed before approval.',
    },
)


class Command(BaseCommand):
    help = 'Seed local development data for EventLight.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing demo events, users, notifications, likes, saves, and RSVPs before seeding.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options['clear']:
            self.clear_demo_data()

        categories = self.seed_categories()
        users = self.seed_users()
        events = self.seed_events(categories, users['demo_organizer'])
        self.seed_engagement(events, users)
        self.seed_notifications(events, users)

        self.stdout.write(self.style.SUCCESS('Seeded EventLight demo data.'))
        self.stdout.write(f'Users: {User.objects.filter(email__endswith="@eventlight.test").count()} demo users')
        self.stdout.write(f'Categories: {Category.objects.count()} total categories')
        self.stdout.write(f'Events: {Event.objects.count()} total events')

    def clear_demo_data(self):
        demo_users = User.objects.filter(email__endswith='@eventlight.test')
        demo_events = Event.objects.filter(created_by__in=demo_users)
        Notification.objects.filter(user__in=demo_users).delete()
        Notification.objects.filter(event__in=demo_events).delete()
        RSVP.objects.filter(user__in=demo_users).delete()
        RSVP.objects.filter(event__in=demo_events).delete()
        EventLike.objects.filter(user__in=demo_users).delete()
        EventLike.objects.filter(event__in=demo_events).delete()
        EventSave.objects.filter(user__in=demo_users).delete()
        EventSave.objects.filter(event__in=demo_events).delete()
        demo_events.delete()
        demo_users.delete()

    def seed_categories(self):
        categories = {}
        for name, slug, icon, description, sort_order in CATEGORIES:
            category, _created = Category.objects.update_or_create(
                slug=slug,
                defaults={
                    'name': name,
                    'icon': icon,
                    'description': description,
                    'sort_order': sort_order,
                    'is_active': True,
                },
            )
            categories[slug] = category
        return categories

    def seed_users(self):
        users = {}
        for user_data in USERS:
            user, created = User.objects.update_or_create(
                email=user_data['email'],
                defaults={
                    'username': user_data['username'],
                    'first_name': user_data['first_name'],
                    'last_name': user_data['last_name'],
                    'city': user_data['city'],
                    'state': 'Lagos State',
                    'country': 'Nigeria',
                    'preferred_categories': user_data['preferred_categories'],
                    'preferred_languages': ['english'],
                    'preferred_age_groups': ['all_ages', 'young_adults'],
                    'email_notifications': True,
                    'event_reminders': True,
                },
            )
            if created:
                user.set_password('password123')
                user.save(update_fields=['password'])
            users[user_data['username']] = user
        return users

    def seed_events(self, categories, organizer):
        now = timezone.now()
        events = []
        for event_data in EVENTS:
            start = now + timedelta(days=event_data['days'])
            end = start + timedelta(hours=event_data['duration_hours'])
            pricing = event_data['pricing']
            event, _created = Event.objects.update_or_create(
                title=event_data['title'],
                created_by=organizer,
                defaults={
                    'description': (
                        f"{event_data['title']} is a demo EventLight event for testing discovery, "
                        'filtering, RSVP, likes, saves, and notifications.'
                    ),
                    'organizer': 'EventLight Demo Church Network',
                    'date': start,
                    'end_date': end,
                    'location': event_data['location'],
                    'location_lat': Decimal(event_data['lat']),
                    'location_lng': Decimal(event_data['lng']),
                    'pricing': pricing,
                    'ticket_price': Decimal(event_data['ticket_price']) if pricing == 'paid' else None,
                    'category': categories[event_data['category']],
                    'language': event_data['language'],
                    'age_group': event_data['age_group'],
                    'capacity': event_data['capacity'],
                    'approval_status': event_data['status'],
                    'rejection_reason': event_data.get('rejection_reason', ''),
                    'is_featured': event_data['featured'],
                },
            )
            events.append(event)
        return events

    def seed_engagement(self, events, users):
        attendees = [users['ada_obi'], users['tunde_balogun'], users['mary_okafor']]
        approved_events = [event for event in events if event.approval_status == 'approved']
        for index, event in enumerate(approved_events):
            EventLike.objects.get_or_create(user=attendees[index % len(attendees)], event=event)
            EventSave.objects.get_or_create(user=attendees[(index + 1) % len(attendees)], event=event)
            RSVP.objects.get_or_create(user=attendees[index % len(attendees)], event=event)
            if index % 2 == 0:
                RSVP.objects.get_or_create(user=attendees[(index + 1) % len(attendees)], event=event)
            if index % 3 == 0:
                EventLike.objects.get_or_create(user=attendees[(index + 2) % len(attendees)], event=event)

    def seed_notifications(self, events, users):
        organizer = users['demo_organizer']
        attendee = users['ada_obi']
        approved_event = next(event for event in events if event.approval_status == 'approved')
        rejected_event = next(event for event in events if event.approval_status == 'rejected')

        Notification.objects.get_or_create(
            user=organizer,
            type='event_approved',
            title='Event approved',
            body=f'{approved_event.title} has been approved.',
            event=approved_event,
            defaults={'detail': 'Your event is now visible in public discovery.'},
        )
        Notification.objects.get_or_create(
            user=organizer,
            type='event_rejected',
            title='Event rejected',
            body=f'{rejected_event.title} was rejected.',
            event=rejected_event,
            defaults={'detail': rejected_event.rejection_reason},
        )
        Notification.objects.get_or_create(
            user=attendee,
            type='rsvp_confirmed',
            title="You're going!",
            body=f'Your RSVP for {approved_event.title} is confirmed.',
            event=approved_event,
            defaults={'detail': 'We will remind you before the event.'},
        )
        Notification.objects.get_or_create(
            user=attendee,
            type='reminder',
            title='Event starts soon',
            body=f'{approved_event.title} is coming up soon.',
            event=approved_event,
            defaults={'detail': 'Plan your movement and arrive early.'},
        )
