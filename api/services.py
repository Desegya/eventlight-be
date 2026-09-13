"""
Shared business logic for notifications and transactional emails.

Both the API views and the Django admin use these helpers so notification
creation and email dispatch stay consistent and DRY.
"""
import logging

import requests as http_requests
from django.conf import settings
from django.template.loader import render_to_string

from .models import Notification

logger = logging.getLogger('api')


def send_template_email(subject, template_name, context, recipient, recipient_name=''):
    api_key = settings.ZEPTOMAIL_API_KEY
    if not api_key:
        return
    html = render_to_string(f'api/emails/{template_name}.html', context)
    text = render_to_string(f'api/emails/{template_name}.txt', context)
    try:
        response = http_requests.post(
            'https://api.zeptomail.com/v1.1/email',
            json={
                'from': {'address': settings.ZEPTOMAIL_FROM_ADDRESS, 'name': settings.ZEPTOMAIL_FROM_NAME},
                'to': [{'email_address': {'address': recipient, 'name': recipient_name or recipient}}],
                'subject': subject,
                'htmlbody': html,
                'textbody': text,
            },
            headers={
                'accept': 'application/json',
                'content-type': 'application/json',
                'authorization': api_key,
            },
            timeout=10,
        )
        if not response.ok:
            logger.error(
                'ZeptoMail send failed (%s) for template=%s recipient=%s: %s',
                response.status_code, template_name, recipient, response.text,
            )
    except Exception:
        logger.exception('ZeptoMail send raised for template=%s recipient=%s', template_name, recipient)


def create_notification(user, type_, title, body, detail='', event=None):
    return Notification.objects.create(
        user=user,
        type=type_,
        title=title,
        body=body,
        detail=detail,
        event=event,
    )


def notify_event_approved(event):
    organizer = event.created_by
    create_notification(
        organizer,
        'event_approved',
        'Event approved',
        f'{event.title} has been approved.',
        event=event,
    )
    if organizer.email_notifications:
        send_template_email(
            subject=f'Your event has been approved - {event.title}',
            template_name='event_approved',
            context={
                'first_name': organizer.first_name or organizer.email,
                'event_title': event.title,
                'event_date': event.date.isoformat() if event.date else '',
                'event_url': f'{settings.FRONTEND_URL}/events/{event.id}',
            },
            recipient=organizer.email,
        )


def notify_event_rejected(event):
    organizer = event.created_by
    create_notification(
        organizer,
        'event_rejected',
        'Event rejected',
        f'{event.title} was rejected.',
        detail=event.rejection_reason,
        event=event,
    )
    if organizer.email_notifications:
        send_template_email(
            subject=f'Update on your event - {event.title}',
            template_name='event_rejected',
            context={
                'first_name': organizer.first_name or organizer.email,
                'event_title': event.title,
                'rejection_reason': event.rejection_reason,
                'event_url': f'{settings.FRONTEND_URL}/events/{event.id}',
            },
            recipient=organizer.email,
        )


def notify_event_cancelled(event):
    """Notify all RSVPed attendees when an event is cancelled or deleted."""
    for rsvp in event.rsvps.select_related('user'):
        attendee = rsvp.user
        create_notification(
            attendee,
            'event_cancelled',
            'Event cancelled',
            f'{event.title} has been cancelled.',
            event=event,
        )
        if attendee.email_notifications:
            send_template_email(
                subject=f'Event cancelled - {event.title}',
                template_name='event_cancelled',
                context={
                    'first_name': attendee.first_name or attendee.email,
                    'event_title': event.title,
                    'event_date': event.date.isoformat() if event.date else '',
                    'event_location': event.location,
                    'browse_url': f'{settings.FRONTEND_URL}/',
                },
                recipient=attendee.email,
            )


def notify_rsvp_confirmed(user, event):
    create_notification(
        user,
        'rsvp_confirmed',
        "You're going!",
        f'Your RSVP for {event.title} is confirmed.',
        event=event,
    )
    if user.email_notifications:
        send_template_email(
            subject=f"You're going to {event.title}!",
            template_name='rsvp_confirmed',
            context={
                'first_name': user.first_name or user.email,
                'event_title': event.title,
                'event_date': event.date.isoformat() if event.date else '',
                'event_location': event.location,
                'event_url': f'{settings.FRONTEND_URL}/events/{event.id}',
            },
            recipient=user.email,
        )


def notify_event_status_change(event):
    """Dispatch the correct notification based on the new approval status."""
    if event.approval_status == 'approved':
        notify_event_approved(event)
    elif event.approval_status == 'rejected':
        notify_event_rejected(event)
