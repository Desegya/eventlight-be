import json
import secrets
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from datetime import timezone as datetime_timezone

from django.conf import settings
from django.contrib.auth import authenticate, update_session_auth_hash
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.core.paginator import EmptyPage, Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from PIL import Image, UnidentifiedImageError

from knox.auth import TokenAuthentication
from knox.models import AuthToken as KnoxAuthToken

from .models import Category, Event, EventLike, EventSave, Notification, PasswordResetToken, RSVP, User


USER_WRITABLE_FIELDS = (
    'first_name',
    'last_name',
    'username',
    'phone_number',
    'street_address',
    'city',
    'state',
    'country',
    'preferred_categories',
    'preferred_languages',
    'preferred_age_groups',
    'max_distance_km',
    'email_notifications',
    'event_reminders',
)

EVENT_FIELDS = (
    'title',
    'description',
    'organizer',
    'date',
    'end_date',
    'location',
    'location_lat',
    'location_lng',
    'pricing',
    'ticket_price',
    'category',
    'language',
    'age_group',
    'capacity',
)

REQUIRED_EVENT_FIELDS = (
    'title',
    'description',
    'date',
    'location',
    'pricing',
    'category',
    'language',
    'age_group',
)

EVENT_FILTER_FIELDS = ('pricing', 'language', 'age_group')
EVENT_ORDERING_FIELDS = {'date', 'created_at', 'title'}
DEFAULT_PAGE_SIZE = 12
MAX_PAGE_SIZE = 50
MAX_IMAGE_SIZE = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {
    'image/jpeg': ('JPEG', '.jpg'),
    'image/png': ('PNG', '.png'),
    'image/webp': ('WEBP', '.webp'),
}


def json_error(detail, status=400):
    return JsonResponse({'detail': detail}, status=status)


def validation_response(errors):
    return JsonResponse(errors, status=400)


def require_methods(request, methods):
    if request.method not in methods:
        return json_error('Method not allowed.', status=405)
    return None


def parse_body(request):
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        return request.POST.dict()
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return None


def authenticate_token(request):
    try:
        result = TokenAuthentication().authenticate(request)
        return result[0] if result else None
    except Exception:
        return None


def require_auth(request):
    user = authenticate_token(request)
    if not user:
        return None, json_error('Authentication credentials were not provided.', status=401)
    return user, None


def require_admin(request):
    user, error = require_auth(request)
    if error:
        return None, error
    if not user.is_staff:
        return None, json_error('You do not have permission to perform this action.', status=403)
    return user, None


def iso_datetime(value):
    if value is None:
        return None
    return value.isoformat().replace('+00:00', 'Z')


def compact_user_payload(user):
    return {
        'id': user.id,
        'first_name': user.first_name,
        'last_name': user.last_name,
    }


def user_payload(user):
    return {
        'id': user.id,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'username': user.username,
        'phone_number': user.phone_number,
        'street_address': user.street_address,
        'city': user.city,
        'state': user.state,
        'country': user.country,
        'preferred_categories': user.preferred_categories,
        'preferred_languages': user.preferred_languages,
        'preferred_age_groups': user.preferred_age_groups,
        'max_distance_km': user.max_distance_km,
        'email_notifications': user.email_notifications,
        'event_reminders': user.event_reminders,
        'date_joined': iso_datetime(user.date_joined),
        'events_created_count': user.events.count(),
        'events_liked_count': user.event_likes.count(),
        'events_saved_count': user.event_saves.count(),
        'events_attending_count': user.event_rsvps.count(),
    }


def public_user_payload(user):
    return {
        'id': user.id,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'events_created_count': user.events.filter(approval_status='approved').count(),
        'date_joined': iso_datetime(user.date_joined),
    }


def compact_category_payload(category):
    return {
        'id': category.id,
        'name': category.name,
        'slug': category.slug,
        'icon': category.icon,
    }


def category_payload(category):
    return {
        **compact_category_payload(category),
        'description': category.description,
        'events_count': category.events.filter(approval_status='approved').count(),
        'is_active': category.is_active,
        'sort_order': category.sort_order,
    }


def decimal_payload(value):
    return float(value) if value is not None else None


def event_payload(event, request=None, user=None):
    image_url = None
    if event.image:
        image_url = event.image.url
        if request:
            image_url = request.build_absolute_uri(image_url)

    is_liked = False
    is_saved = False
    is_rsvped = False
    if user and user.is_authenticated:
        is_liked = EventLike.objects.filter(user=user, event=event).exists()
        is_saved = EventSave.objects.filter(user=user, event=event).exists()
        is_rsvped = RSVP.objects.filter(user=user, event=event).exists()

    return {
        'id': event.id,
        'title': event.title,
        'description': event.description,
        'organizer': event.organizer,
        'date': iso_datetime(event.date),
        'end_date': iso_datetime(event.end_date),
        'location': event.location,
        'location_lat': decimal_payload(event.location_lat),
        'location_lng': decimal_payload(event.location_lng),
        'pricing': event.pricing,
        'ticket_price': decimal_payload(event.ticket_price),
        'category': compact_category_payload(event.category),
        'language': event.language,
        'age_group': event.age_group,
        'capacity': event.capacity,
        'rsvp_count': event.rsvps.count(),
        'is_rsvped': is_rsvped,
        'is_full': event.is_full,
        'is_featured': event.is_featured,
        'approval_status': event.approval_status,
        'rejection_reason': event.rejection_reason or None,
        'image': image_url,
        'created_by': compact_user_payload(event.created_by),
        'is_liked': is_liked,
        'is_saved': is_saved,
        'likes_count': event.likes.count(),
        'saves_count': event.saves.count(),
        'created_at': iso_datetime(event.created_at),
        'updated_at': iso_datetime(event.updated_at),
    }


def compact_event_payload(event, request=None):
    image_url = None
    if event and event.image:
        image_url = event.image.url
        if request:
            image_url = request.build_absolute_uri(image_url)
    return {
        'id': event.id,
        'title': event.title,
        'image': image_url,
    }


def notification_payload(notification, request=None):
    return {
        'id': notification.id,
        'type': notification.type,
        'title': notification.title,
        'body': notification.body,
        'detail': notification.detail,
        'event': compact_event_payload(notification.event, request=request) if notification.event else None,
        'is_read': notification.is_read,
        'created_at': iso_datetime(notification.created_at),
    }


def positive_int(value, default):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def paginated_response(request, items, mapper):
    page_size = min(positive_int(request.GET.get('page_size'), DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
    page_number = positive_int(request.GET.get('page'), 1)
    paginator = Paginator(items, page_size)

    try:
        page = paginator.page(page_number)
    except EmptyPage:
        page = paginator.page(paginator.num_pages or 1)

    def page_url(target_page):
        params = request.GET.copy()
        params['page'] = target_page
        return request.build_absolute_uri(f'{request.path}?{params.urlencode()}')

    return JsonResponse(
        {
            'count': paginator.count,
            'next': page_url(page.next_page_number()) if page.has_next() else None,
            'previous': page_url(page.previous_page_number()) if page.has_previous() else None,
            'results': [mapper(item) for item in page.object_list],
        }
    )


def password_errors(password):
    if len(password or '') < 8:
        return ['This password is too short. It must contain at least 8 characters.']
    return []


def parse_event_datetime(value):
    parsed = parse_datetime(value) if value else None
    if not parsed:
        raise ValueError('Enter a valid ISO datetime.')
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone=datetime_timezone.utc)
    return parsed


def parse_decimal(value, field):
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f'Enter a valid number for {field}.')


def parse_nullable_int(value, field):
    if value in (None, ''):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f'Enter a valid integer for {field}.')
    if parsed < 0:
        raise ValueError(f'{field} cannot be negative.')
    return parsed


def parse_bool(value):
    return str(value).lower() in {'1', 'true', 'yes', 'on'}


def validate_and_process_image(upload):
    if not upload:
        return None, None
    if upload.size > MAX_IMAGE_SIZE:
        return None, ['Image must not exceed 10 MB.']
    if upload.content_type not in ALLOWED_IMAGE_TYPES:
        return None, ['Upload a JPEG, PNG, or WEBP image.']

    image_format, extension = ALLOWED_IMAGE_TYPES[upload.content_type]
    try:
        upload.seek(0)
        image = Image.open(upload)
        image.verify()
        upload.seek(0)
        image = Image.open(upload)
    except (UnidentifiedImageError, OSError):
        return None, ['Upload a valid image file.']

    if image.width > 1200:
        ratio = 1200 / image.width
        image = image.resize((1200, int(image.height * ratio)), Image.Resampling.LANCZOS)
    if image_format == 'JPEG' and image.mode not in {'RGB', 'L'}:
        image = image.convert('RGB')

    buffer = BytesIO()
    image.save(buffer, format=image_format)
    filename = f'{slugify(upload.name.rsplit(".", 1)[0]) or "event-image"}{extension}'
    return ContentFile(buffer.getvalue(), name=filename), None


def get_event(event_id):
    return Event.objects.select_related('created_by', 'category').filter(id=event_id).first()


def get_visible_event(event_id, user=None):
    event = get_event(event_id)
    if not event:
        return None
    if event.approval_status == 'approved':
        return event
    if user and (event.created_by_id == user.id or user.is_staff):
        return event
    return None


def send_template_email(subject, template_name, context, recipient):
    html = render_to_string(f'api/emails/{template_name}.html', context)
    text = render_to_string(f'api/emails/{template_name}.txt', context)
    send_mail(
        subject=subject,
        message=text,
        html_message=html,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[recipient],
        fail_silently=True,
    )


def create_notification(user, type_, title, body, detail='', event=None):
    return Notification.objects.create(
        user=user,
        type=type_,
        title=title,
        body=body,
        detail=detail,
        event=event,
    )


def filtered_events(query_params):
    events = Event.objects.filter(approval_status='approved').select_related('created_by', 'category')
    search = (query_params.get('search') or '').strip()
    if search:
        events = events.filter(
            Q(title__icontains=search)
            | Q(description__icontains=search)
            | Q(location__icontains=search)
        )

    category = (query_params.get('category') or '').strip()
    if category:
        events = events.filter(category__slug=category)

    for field in EVENT_FILTER_FIELDS:
        value = (query_params.get(field) or '').strip()
        if value:
            events = events.filter(**{field: value})

    if 'is_featured' in query_params:
        events = events.filter(is_featured=parse_bool(query_params.get('is_featured')))

    ordering = (query_params.get('ordering') or 'date').strip()
    normalized_ordering = ordering[1:] if ordering.startswith('-') else ordering
    if normalized_ordering not in EVENT_ORDERING_FIELDS:
        ordering = 'date'
    return events.order_by(ordering)


def apply_event_data(event, data, partial=False, acting_user=None):
    errors = {}
    for field in EVENT_FIELDS:
        if field not in data:
            if not partial and field in REQUIRED_EVENT_FIELDS:
                errors[field] = ['This field is required.']
            continue
        value = data.get(field)
        if value in (None, ''):
            if not partial and field in REQUIRED_EVENT_FIELDS:
                errors[field] = ['This field is required.']
                continue
            if field in {'end_date', 'location_lat', 'location_lng', 'ticket_price', 'capacity'}:
                setattr(event, field, None)
            elif field == 'category':
                errors[field] = ['This field is required.']
            else:
                setattr(event, field, '')
            continue

        try:
            if field in {'date', 'end_date'}:
                value = parse_event_datetime(value)
            elif field in {'location_lat', 'location_lng', 'ticket_price'}:
                value = parse_decimal(value, field)
            elif field == 'capacity':
                value = parse_nullable_int(value, field)
            elif field == 'category':
                category = Category.objects.filter(slug=value, is_active=True).first()
                if not category:
                    errors[field] = ['Select a valid category.']
                    continue
                value = category
        except ValueError as exc:
            errors[field] = [str(exc)]
            continue

        setattr(event, field, value)

    if acting_user and acting_user.is_staff:
        if 'is_featured' in data:
            event.is_featured = parse_bool(data.get('is_featured'))
        if 'approval_status' in data:
            if data['approval_status'] not in {'pending', 'approved', 'rejected'}:
                errors['approval_status'] = ['Select a valid approval status.']
            else:
                event.approval_status = data['approval_status']
        if 'rejection_reason' in data:
            event.rejection_reason = data.get('rejection_reason') or ''

    if event.end_date and event.date and event.end_date <= event.date:
        errors['end_date'] = ['End date must be after start date.']
    if event.pricing == 'paid' and event.ticket_price is None:
        errors['ticket_price'] = ['This field is required when pricing is paid.']
    if event.pricing == 'free':
        event.ticket_price = None
    return errors


@csrf_exempt
def register(request):
    error = require_methods(request, ['POST'])
    if error:
        return error

    data = parse_body(request)
    if data is None:
        return json_error('Invalid JSON.', status=400)

    errors = {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    username = (data.get('username') or email).strip()

    if not email:
        errors['email'] = ['This field is required.']
    if User.objects.filter(email=email).exists():
        errors['email'] = ['A user with this email already exists.']
    if not password:
        errors['password'] = ['This field is required.']
    else:
        password_validation_errors = password_errors(password)
        if password_validation_errors:
            errors['password'] = password_validation_errors

    if errors:
        return validation_response(errors)

    try:
        user = User.objects.create_user(
            email=email,
            username=username,
            password=password,
            first_name=data.get('first_name', ''),
            last_name=data.get('last_name', ''),
        )
    except IntegrityError:
        return validation_response({'email': ['A user with this email or username already exists.']})

    _, token = KnoxAuthToken.objects.create(user=user)  # type: ignore[misc]

    send_template_email(
        subject=f'Welcome to EventLight, {user.first_name or user.email}!',
        template_name='welcome',
        context={
            'first_name': user.first_name or user.email,
            'browse_url': f'{settings.FRONTEND_URL}/',
        },
        recipient=user.email,
    )

    return JsonResponse({'key': token, 'user': user_payload(user)}, status=201)


@csrf_exempt
def login(request):
    error = require_methods(request, ['POST'])
    if error:
        return error

    data = parse_body(request)
    if data is None:
        return json_error('Invalid JSON.', status=400)

    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    user = authenticate(request, username=email, password=password)
    if not user:
        return json_error('Invalid credentials.', status=400)

    _, token = KnoxAuthToken.objects.create(user=user)  # type: ignore[misc]
    return JsonResponse({'key': token, 'user': user_payload(user)})


@csrf_exempt
def logout(request):
    error = require_methods(request, ['POST'])
    if error:
        return error

    _, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    try:
        result = TokenAuthentication().authenticate(request)
        if result:
            result[1].delete()
    except Exception:
        pass
    return JsonResponse({'detail': 'Logged out successfully.'})


@csrf_exempt
def current_user(request):
    error = require_methods(request, ['GET', 'PATCH'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    if request.method == 'GET':
        return JsonResponse(user_payload(user))

    data = parse_body(request)
    if data is None:
        return json_error('Invalid JSON.', status=400)

    for field in USER_WRITABLE_FIELDS:
        if field in data:
            setattr(user, field, data[field])
    try:
        user.save()
    except IntegrityError:
        return validation_response({'username': ['A user with this username already exists.']})
    return JsonResponse(user_payload(user))


@csrf_exempt
def change_password(request):
    error = require_methods(request, ['POST'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    data = parse_body(request)
    if data is None:
        return json_error('Invalid JSON.', status=400)

    if not user.check_password(data.get('old_password', '')):
        return validation_response({'old_password': ['Your old password was entered incorrectly.']})
    if data.get('new_password1') != data.get('new_password2'):
        return validation_response({'new_password2': ['The two password fields did not match.']})

    new_password_errors = password_errors(data.get('new_password1') or '')
    if new_password_errors:
        return validation_response({'new_password1': new_password_errors})

    user.set_password(data['new_password1'])
    user.save()
    update_session_auth_hash(request, user)
    return JsonResponse({'detail': 'Password changed successfully.'})


@csrf_exempt
def password_reset(request):
    error = require_methods(request, ['POST'])
    if error:
        return error

    data = parse_body(request)
    if data is None:
        return json_error('Invalid JSON.', status=400)

    email = (data.get('email') or '').strip().lower()
    if not email:
        return validation_response({'email': ['This field is required.']})

    # Always respond the same way — don't leak whether the email exists
    user = User.objects.filter(email=email).first()
    if user:
        token = secrets.token_urlsafe(32)
        PasswordResetToken.objects.create(user=user, token=token)
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        send_template_email(
            subject='Reset your EventLight password',
            template_name='password_reset',
            context={
                'first_name': user.first_name or user.email,
                'reset_url': reset_url,
            },
            recipient=user.email,
        )

    return JsonResponse({'detail': 'If that email is registered, a reset link has been sent.'})


@csrf_exempt
def password_reset_confirm(request):
    error = require_methods(request, ['POST'])
    if error:
        return error

    data = parse_body(request)
    if data is None:
        return json_error('Invalid JSON.', status=400)

    token_value = (data.get('token') or '').strip()
    new_password1 = data.get('new_password1') or ''
    new_password2 = data.get('new_password2') or ''

    errors = {}
    if not token_value:
        errors['token'] = ['This field is required.']
    if not new_password1:
        errors['new_password1'] = ['This field is required.']
    if errors:
        return validation_response(errors)

    if new_password1 != new_password2:
        return validation_response({'new_password2': ['The two password fields did not match.']})

    pw_errors = password_errors(new_password1)
    if pw_errors:
        return validation_response({'new_password1': pw_errors})

    reset_token = (
        PasswordResetToken.objects
        .select_related('user')
        .filter(token=token_value, is_used=False)
        .first()
    )
    expiry = timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT_SECONDS)
    if not reset_token or (timezone.now() - reset_token.created_at) > expiry:
        return validation_response({'token': ['This reset link is invalid or has expired.']})

    reset_token.is_used = True
    reset_token.save(update_fields=['is_used'])

    reset_token.user.set_password(new_password1)
    reset_token.user.save()

    return JsonResponse({'detail': 'Password reset complete. You can now log in.'})


@csrf_exempt
def categories_collection(request):
    error = require_methods(request, ['GET', 'POST'])
    if error:
        return error

    if request.method == 'GET':
        categories = Category.objects.filter(is_active=True)
        return JsonResponse([category_payload(category) for category in categories], safe=False)

    _user, auth_error = require_admin(request)
    if auth_error:
        return auth_error

    data = parse_body(request)
    if data is None:
        return json_error('Invalid JSON.', status=400)
    name = (data.get('name') or '').strip()
    slug = (data.get('slug') or slugify(name)).strip()
    if not name:
        return validation_response({'name': ['This field is required.']})
    if not slug:
        return validation_response({'slug': ['This field is required.']})
    if Category.objects.filter(slug=slug).exists():
        return validation_response({'slug': ['A category with this slug already exists.']})

    category = Category.objects.create(
        name=name,
        slug=slug,
        icon=data.get('icon') or 'zap',
        description=data.get('description') or '',
        sort_order=positive_int(data.get('sort_order'), 0),
        is_active=parse_bool(data.get('is_active')) if 'is_active' in data else True,
    )
    return JsonResponse(category_payload(category), status=201)


@csrf_exempt
def category_detail(request, category_id):
    error = require_methods(request, ['PATCH', 'DELETE'])
    if error:
        return error

    _user, auth_error = require_admin(request)
    if auth_error:
        return auth_error

    category = Category.objects.filter(id=category_id).first()
    if not category:
        return json_error('Not found.', status=404)

    if request.method == 'DELETE':
        category.is_active = False
        category.save(update_fields=['is_active', 'updated_at'])
        return JsonResponse(category_payload(category))

    data = parse_body(request)
    if data is None:
        return json_error('Invalid JSON.', status=400)
    for field in ('name', 'slug', 'icon', 'description', 'sort_order', 'is_active'):
        if field in data:
            setattr(category, field, data[field])
    if 'sort_order' in data:
        category.sort_order = positive_int(data.get('sort_order'), 0)
    if 'is_active' in data:
        category.is_active = parse_bool(data.get('is_active'))
    if 'slug' in data and Category.objects.exclude(id=category.id).filter(slug=category.slug).exists():
        return validation_response({'slug': ['A category with this slug already exists.']})
    category.save()
    return JsonResponse(category_payload(category))


@csrf_exempt
def events_collection(request):
    error = require_methods(request, ['GET', 'POST'])
    if error:
        return error

    user = authenticate_token(request)
    if request.method == 'GET':
        events = filtered_events(request.GET)
        return paginated_response(request, events, lambda event: event_payload(event, request=request, user=user))

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    data = parse_body(request)
    if data is None:
        return json_error('Invalid JSON.', status=400)

    event = Event(created_by=user, approval_status='pending')
    errors = apply_event_data(event, data, partial=False, acting_user=user)
    if request.FILES.get('image'):
        processed_image, image_errors = validate_and_process_image(request.FILES['image'])
        if image_errors:
            errors['image'] = image_errors
        else:
            event.image = processed_image
    if errors:
        return validation_response(errors)
    event.save()
    return JsonResponse(event_payload(event, request=request, user=user), status=201)


@csrf_exempt
def event_detail(request, event_id):
    error = require_methods(request, ['GET', 'PATCH', 'DELETE'])
    if error:
        return error

    user = authenticate_token(request)
    event = get_visible_event(event_id, user=user)
    if not event:
        return json_error('Not found.', status=404)

    if request.method == 'GET':
        return JsonResponse(event_payload(event, request=request, user=user))

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error
    if event.created_by_id != user.id and not user.is_staff:
        return json_error('You do not have permission to modify this event.', status=403)

    if request.method == 'DELETE':
        if event.approval_status == 'approved':
            event_date = iso_datetime(event.date) or ''
            browse_url = f'{settings.FRONTEND_URL}/'
            for rsvp in event.rsvps.select_related('user'):
                attendee = rsvp.user
                create_notification(attendee, 'event_cancelled', 'Event cancelled', f'{event.title} has been cancelled.', event=event)
                if attendee.email_notifications:
                    send_template_email(
                        subject=f'Event cancelled — {event.title}',
                        template_name='event_cancelled',
                        context={'first_name': attendee.first_name or attendee.email, 'event_title': event.title, 'event_date': event_date, 'event_location': event.location, 'browse_url': browse_url},
                        recipient=attendee.email,
                    )
        event.delete()
        return JsonResponse({'detail': 'Event deleted successfully.'})

    data = parse_body(request)
    if data is None:
        return json_error('Invalid JSON.', status=400)

    old_status = event.approval_status
    errors = apply_event_data(event, data, partial=True, acting_user=user)
    if request.FILES.get('image'):
        processed_image, image_errors = validate_and_process_image(request.FILES['image'])
        if image_errors:
            errors['image'] = image_errors
        else:
            event.image = processed_image
    if errors:
        return validation_response(errors)
    event.save()

    if user.is_staff and old_status != event.approval_status:
        organizer = event.created_by
        event_url = f'{settings.FRONTEND_URL}/events/{event.id}'
        event_date = iso_datetime(event.date) or ''
        if event.approval_status == 'approved':
            create_notification(organizer, 'event_approved', 'Event approved', f'{event.title} has been approved.', event=event)
            if organizer.email_notifications:
                send_template_email(
                    subject=f'Your event has been approved — {event.title}',
                    template_name='event_approved',
                    context={'first_name': organizer.first_name or organizer.email, 'event_title': event.title, 'event_date': event_date, 'event_url': event_url},
                    recipient=organizer.email,
                )
        elif event.approval_status == 'rejected':
            create_notification(organizer, 'event_rejected', 'Event rejected', f'{event.title} was rejected.', detail=event.rejection_reason, event=event)
            if organizer.email_notifications:
                send_template_email(
                    subject=f'Update on your event — {event.title}',
                    template_name='event_rejected',
                    context={'first_name': organizer.first_name or organizer.email, 'event_title': event.title, 'rejection_reason': event.rejection_reason, 'event_url': event_url},
                    recipient=organizer.email,
                )

    return JsonResponse(event_payload(event, request=request, user=user))


def related_events(request, event_id):
    error = require_methods(request, ['GET'])
    if error:
        return error

    user = authenticate_token(request)
    event = get_visible_event(event_id, user=user)
    if not event:
        return json_error('Not found.', status=404)

    events = (
        Event.objects.filter(category=event.category, approval_status='approved')
        .exclude(id=event.id)
        .select_related('created_by', 'category')
        .order_by('date')[:6]
    )
    return JsonResponse(
        {
            'count': len(events),
            'results': [event_payload(related, request=request, user=user) for related in events],
        }
    )


@csrf_exempt
def toggle_like(request, event_id):
    error = require_methods(request, ['POST'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    event = get_visible_event(event_id, user=user)
    if not event:
        return json_error('Not found.', status=404)
    like, created = EventLike.objects.get_or_create(user=user, event=event)
    if created:
        return JsonResponse({'liked': True, 'likes_count': event.likes.count(), 'message': 'Event liked'})
    like.delete()
    return JsonResponse({'liked': False, 'likes_count': event.likes.count(), 'message': 'Event unliked'})


@csrf_exempt
def toggle_save(request, event_id):
    error = require_methods(request, ['POST'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    event = get_visible_event(event_id, user=user)
    if not event:
        return json_error('Not found.', status=404)
    save, created = EventSave.objects.get_or_create(user=user, event=event)
    if created:
        return JsonResponse({'saved': True, 'saves_count': event.saves.count(), 'message': 'Event saved'})
    save.delete()
    return JsonResponse({'saved': False, 'saves_count': event.saves.count(), 'message': 'Event unsaved'})


@csrf_exempt
def toggle_rsvp(request, event_id):
    error = require_methods(request, ['POST'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error
    assert user is not None

    event = get_visible_event(event_id, user=user)
    if not event:
        return json_error('Not found.', status=404)

    existing = RSVP.objects.filter(user=user, event=event).first()
    if existing:
        existing.delete()
        return JsonResponse(
            {
                'rsvped': False,
                'rsvp_count': event.rsvps.count(),
                'message': "You're no longer going.",
            }
        )

    if event.is_full:
        return json_error('This event is at full capacity.', status=400)

    RSVP.objects.create(user=user, event=event)
    create_notification(user, 'rsvp_confirmed', "You're going!", f'Your RSVP for {event.title} is confirmed.', event=event)
    if user.email_notifications:
        send_template_email(
            subject=f"You're going to {event.title}!",
            template_name='rsvp_confirmed',
            context={'first_name': user.first_name or user.email, 'event_title': event.title, 'event_date': iso_datetime(event.date) or '', 'event_location': event.location, 'event_url': f'{settings.FRONTEND_URL}/events/{event.id}'},
            recipient=user.email,
        )
    return JsonResponse(
        {
            'rsvped': True,
            'rsvp_count': event.rsvps.count(),
            'message': "You're going! We'll remind you before the event.",
        }
    )


def event_attendees(request, event_id):
    error = require_methods(request, ['GET'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    event = get_event(event_id)
    if not event:
        return json_error('Not found.', status=404)
    if event.created_by_id != user.id and not user.is_staff:
        return json_error('You do not have permission to view attendees for this event.', status=403)

    attendees = [
        {
            'id': rsvp.user.id,
            'first_name': rsvp.user.first_name,
            'last_name': rsvp.user.last_name,
            'email': rsvp.user.email,
            'rsvped_at': iso_datetime(rsvp.created_at),
        }
        for rsvp in event.rsvps.select_related('user').order_by('-created_at')
    ]
    return JsonResponse({'count': len(attendees), 'results': attendees})


def liked_events(request):
    error = require_methods(request, ['GET'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    events = Event.objects.filter(likes__user=user, approval_status='approved').select_related('created_by', 'category')
    payload = [event_payload(event, request=request, user=user) for event in events]
    return JsonResponse(payload, safe=False)


def saved_events(request):
    error = require_methods(request, ['GET'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    events = Event.objects.filter(saves__user=user, approval_status='approved').select_related('created_by', 'category')
    payload = [event_payload(event, request=request, user=user) for event in events]
    return JsonResponse(payload, safe=False)


def my_events(request):
    error = require_methods(request, ['GET'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    events = Event.objects.filter(created_by=user).select_related('created_by', 'category')
    payload = [event_payload(event, request=request, user=user) for event in events]
    return JsonResponse(payload, safe=False)


def attending_events(request):
    error = require_methods(request, ['GET'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    events = Event.objects.filter(rsvps__user=user, approval_status='approved').select_related('created_by', 'category')
    payload = [event_payload(event, request=request, user=user) for event in events]
    return JsonResponse(payload, safe=False)


def public_user(request, user_id):
    error = require_methods(request, ['GET'])
    if error:
        return error

    user = User.objects.filter(id=user_id).first()
    if not user:
        return json_error('Not found.', status=404)
    return JsonResponse(public_user_payload(user))


def public_user_events(request, user_id):
    error = require_methods(request, ['GET'])
    if error:
        return error

    owner = User.objects.filter(id=user_id).first()
    if not owner:
        return json_error('Not found.', status=404)
    user = authenticate_token(request)
    events = Event.objects.filter(created_by=owner, approval_status='approved').select_related('created_by', 'category')
    return paginated_response(request, events, lambda event: event_payload(event, request=request, user=user))


def notifications_collection(request):
    error = require_methods(request, ['GET'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    notifications = Notification.objects.filter(user=user).select_related('event')
    if 'is_read' in request.GET:
        notifications = notifications.filter(is_read=parse_bool(request.GET.get('is_read')))
    return paginated_response(
        request,
        notifications,
        lambda notification: notification_payload(notification, request=request),
    )


@csrf_exempt
def mark_notification_read(request, notification_id):
    error = require_methods(request, ['POST'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    notification = Notification.objects.filter(id=notification_id, user=user).first()
    if not notification:
        return json_error('Not found.', status=404)
    notification.is_read = True
    notification.save(update_fields=['is_read'])
    return JsonResponse(notification_payload(notification, request=request))


@csrf_exempt
def mark_all_notifications_read(request):
    error = require_methods(request, ['POST'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    updated = Notification.objects.filter(user=user, is_read=False).update(is_read=True)
    return JsonResponse({'updated': updated})


def unread_notifications_count(request):
    error = require_methods(request, ['GET'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error
    return JsonResponse({'count': Notification.objects.filter(user=user, is_read=False).count()})


@csrf_exempt
def delete_notification(request, notification_id):
    error = require_methods(request, ['DELETE'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    deleted, _ = Notification.objects.filter(id=notification_id, user=user).delete()
    if not deleted:
        return json_error('Not found.', status=404)
    return HttpResponse(status=204)


def api_not_found(request, exception=None, **_kwargs):
    return json_error('Not found.', status=404)


def api_server_error(request):
    return json_error('An unexpected error occurred.', status=500)
