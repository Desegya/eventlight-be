from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from api.models import Event, Notification, User
from api.views import create_notification, display_datetime, send_template_email


class Command(BaseCommand):
    help = (
        'Notify users about approved events they RSVPed to or saved that start soon. '
        'Safe to run repeatedly (e.g. hourly from a scheduler): each user is reminded once per event.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--hours', type=int, default=24, help='Look-ahead window in hours (default 24).')

    def handle(self, *args, **options):
        now = timezone.now()
        events = Event.objects.filter(
            approval_status='approved',
            date__gt=now,
            date__lte=now + timedelta(hours=options['hours']),
        )
        sent = 0
        for event in events:
            already_reminded = Notification.objects.filter(event=event, type='reminder').values('user_id')
            recipients = (
                User.objects.filter(Q(event_rsvps__event=event) | Q(event_saves__event=event), event_reminders=True, is_active=True)
                .exclude(id__in=already_reminded)
                .distinct()
            )
            event_url = f'{settings.FRONTEND_URL}/events/{event.id}'
            for user in recipients:
                create_notification(user, 'reminder', 'Event reminder', f'{event.title} starts soon.', event=event)
                if user.email_notifications:
                    send_template_email(
                        subject=f'Reminder: {event.title} is coming up',
                        template_name='event_reminder',
                        context={
                            'first_name': user.first_name or user.email,
                            'event_title': event.title,
                            'event_date': display_datetime(event.date),
                            'event_location': event.location,
                            'event_url': event_url,
                        },
                        recipient=user.email,
                    )
                sent += 1
        self.stdout.write(self.style.SUCCESS(f'Sent {sent} reminder(s).'))
