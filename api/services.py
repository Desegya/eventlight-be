"""
Shared business logic for notifications and transactional emails.

Both the API views and the Django admin use these helpers so notification
creation and email dispatch stay consistent and DRY.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timezone as datetime_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests as http_requests
from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Notification

logger = logging.getLogger('api')

ZEPTOMAIL_API_URL = 'https://api.zeptomail.com/v1.1/email'

_email_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='email')


def mask_email(address):
    local, _, domain = (address or '').partition('@')
    return f'{local[:1]}***@{domain}' if domain else '***'


def display_datetime(value):
    """Human-readable time for emails, in the audience's timezone rather than UTC."""
    if value is None:
        return ''
    try:
        zone = ZoneInfo(settings.DISPLAY_TIME_ZONE)
    except ZoneInfoNotFoundError:  # slim images may ship without tz data
        zone = datetime_timezone.utc
    local = timezone.localtime(value, zone)
    return f"{local.strftime('%A, %d %B %Y at %I:%M %p').replace(' 0', ' ')} {local.tzname()}"


def deliver_email(payload, template_name):
    recipient = mask_email(payload['to'][0]['email_address']['address'])
    try:
        response = http_requests.post(
            ZEPTOMAIL_API_URL,
            json=payload,
            headers={
                'accept': 'application/json',
                'content-type': 'application/json',
                'authorization': settings.ZEPTOMAIL_API_KEY,
            },
            timeout=10,
        )
        if not response.ok:
            logger.error(
                'ZeptoMail send failed (%s) for template=%s recipient=%s: %s',
                response.status_code, template_name, recipient, response.text[:500],
            )
    except Exception:
        logger.exception('ZeptoMail send raised for template=%s recipient=%s', template_name, recipient)


def send_template_email(subject, template_name, context, recipient, recipient_name=''):
    if not settings.ZEPTOMAIL_API_KEY:
        return
    payload = {
        'from': {'address': settings.ZEPTOMAIL_FROM_ADDRESS, 'name': settings.ZEPTOMAIL_FROM_NAME},
        'to': [{'email_address': {'address': recipient, 'name': recipient_name or recipient}}],
        'subject': subject,
        'htmlbody': render_to_string(f'api/emails/{template_name}.html', context),
        'textbody': render_to_string(f'api/emails/{template_name}.txt', context),
    }
    if not settings.EMAIL_SEND_ASYNC:
        deliver_email(payload, template_name)
        return
    # Delivery happens off the request thread so a slow mail API cannot push a
    # request past the gunicorn worker timeout (cancelling an event emails every
    # attendee), and only after commit so no email describes a rolled-back change.
    transaction.on_commit(lambda: _email_executor.submit(deliver_email, payload, template_name))


def create_notification(user, type_, title, body, detail='', event=None):
    return Notification.objects.create(
        user=user,
        type=type_,
        title=title,
        body=body,
        detail=detail,
        event=event,
    )


def event_url(event):
    return f'{settings.FRONTEND_URL}/events/{event.id}'


def notify_event_approved(event):
    organizer = event.created_by
    create_notification(organizer, 'event_approved', 'Event approved', f'{event.title} has been approved.', event=event)
    if organizer.email_notifications:
        send_template_email(
            subject=f'Your event has been approved — {event.title}',
            template_name='event_approved',
            context={
                'first_name': organizer.first_name or organizer.email,
                'event_title': event.title,
                'event_date': display_datetime(event.date),
                'event_url': event_url(event),
            },
            recipient=organizer.email,
        )


def notify_event_rejected(event):
    organizer = event.created_by
    create_notification(
        organizer, 'event_rejected', 'Event rejected', f'{event.title} was rejected.',
        detail=event.rejection_reason, event=event,
    )
    if organizer.email_notifications:
        send_template_email(
            subject=f'Update on your event — {event.title}',
            template_name='event_rejected',
            context={
                'first_name': organizer.first_name or organizer.email,
                'event_title': event.title,
                'rejection_reason': event.rejection_reason,
                'event_url': event_url(event),
            },
            recipient=organizer.email,
        )


def notify_event_cancelled(event):
    """Notify RSVPed attendees when a published event is deleted. Pending or
    rejected events were never public, so there is nobody to tell."""
    if event.approval_status != 'approved':
        return
    for rsvp in event.rsvps.select_related('user'):
        attendee = rsvp.user
        create_notification(attendee, 'event_cancelled', 'Event cancelled', f'{event.title} has been cancelled.', event=event)
        if attendee.email_notifications:
            send_template_email(
                subject=f'Event cancelled — {event.title}',
                template_name='event_cancelled',
                context={
                    'first_name': attendee.first_name or attendee.email,
                    'event_title': event.title,
                    'event_date': display_datetime(event.date),
                    'event_location': event.location,
                    'browse_url': f'{settings.FRONTEND_URL}/',
                },
                recipient=attendee.email,
            )


def notify_rsvp_confirmed(user, event):
    create_notification(user, 'rsvp_confirmed', "You're going!", f'Your RSVP for {event.title} is confirmed.', event=event)
    if user.email_notifications:
        send_template_email(
            subject=f"You're going to {event.title}!",
            template_name='rsvp_confirmed',
            context={
                'first_name': user.first_name or user.email,
                'event_title': event.title,
                'event_date': display_datetime(event.date),
                'event_location': event.location,
                'event_url': event_url(event),
            },
            recipient=user.email,
        )


def notify_event_reminder(user, event):
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
                'event_url': event_url(event),
            },
            recipient=user.email,
        )


def notify_event_status_change(event):
    """Dispatch the correct notification based on the new approval status."""
    if event.approval_status == 'approved':
        notify_event_approved(event)
    elif event.approval_status == 'rejected':
        notify_event_rejected(event)
