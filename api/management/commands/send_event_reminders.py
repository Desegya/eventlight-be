from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from api.models import Event, Notification, User
from api.services import notify_event_reminder


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
            for user in recipients:
                notify_event_reminder(user, event)
                sent += 1
        self.stdout.write(self.style.SUCCESS(f'Sent {sent} reminder(s).'))
