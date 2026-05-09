import json
from datetime import timezone as datetime_timezone

from django.contrib.auth import authenticate, update_session_auth_hash
from django.db import IntegrityError
from django.http import JsonResponse
from django.core.paginator import EmptyPage, Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt

from .models import AuthToken, Category, Event, EventLike, EventSave, User


USER_FIELDS = (
    'id',
    'email',
    'first_name',
    'last_name',
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
    'location',
    'pricing',
    'category',
    'event_type',
    'language',
    'age_group',
)

OPTIONAL_EVENT_FIELDS = {'organizer'}
EVENT_FILTER_FIELDS = ('category', 'pricing', 'event_type', 'language', 'age_group')
EVENT_ORDERING_FIELDS = {'date', 'created_at', 'title'}
DEFAULT_PAGE_SIZE = 12
MAX_PAGE_SIZE = 50


def json_error(detail, status=400):
    return JsonResponse({'detail': detail}, status=status)


def parse_body(request):
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        return request.POST.dict()
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return None


def require_methods(request, methods):
    if request.method not in methods:
        return JsonResponse({'detail': 'Method not allowed.'}, status=405)
    return None


def authenticate_token(request):
    header = request.headers.get('Authorization', '')
    if not header.startswith('Token '):
        return None
    key = header.split(' ', 1)[1].strip()
    token = AuthToken.objects.select_related('user').filter(key=key).first()
    return token.user if token else None


def require_auth(request):
    user = authenticate_token(request)
    if not user:
        return None, json_error('Authentication credentials were not provided.', status=401)
    return user, None


def user_payload(user):
    return {field: getattr(user, field) for field in USER_FIELDS}


def event_payload(event, request=None, user=None):
    image_url = None
    if event.image:
        image_url = event.image.url
        if request:
            image_url = request.build_absolute_uri(image_url)

    is_liked = False
    is_saved = False
    if user and user.is_authenticated:
        is_liked = EventLike.objects.filter(user=user, event=event).exists()
        is_saved = EventSave.objects.filter(user=user, event=event).exists()

    return {
        'id': event.id,
        'title': event.title,
        'description': event.description,
        'organizer': event.organizer,
        'date': event.date.isoformat().replace('+00:00', 'Z'),
        'location': event.location,
        'pricing': event.pricing,
        'category': event.category,
        'event_type': event.event_type,
        'language': event.language,
        'age_group': event.age_group,
        'created_by': event.created_by_id,
        'approval_status': event.approval_status,
        'image': image_url,
        'created_at': event.created_at.isoformat().replace('+00:00', 'Z'),
        'is_liked': is_liked,
        'is_saved': is_saved,
        'likes_count': event.likes.count(),
        'saves_count': event.saves.count(),
    }


def category_payload(category):
    return {
        'id': category.id,
        'name': category.name,
        'slug': category.slug,
        'description': category.description,
        'is_active': category.is_active,
    }


def positive_int(value, default):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def filtered_events(query_params):
    events = Event.objects.filter(approval_status='approved').select_related('created_by')
    search = (query_params.get('search') or '').strip()
    if search:
        events = events.filter(
            Q(title__icontains=search)
            | Q(description__icontains=search)
            | Q(location__icontains=search)
        )

    for field in EVENT_FILTER_FIELDS:
        value = (query_params.get(field) or '').strip()
        if value:
            events = events.filter(**{field: value})

    ordering = (query_params.get('ordering') or 'date').strip()
    normalized_ordering = ordering[1:] if ordering.startswith('-') else ordering
    if normalized_ordering not in EVENT_ORDERING_FIELDS:
        ordering = 'date'
    return events.order_by(ordering)


def paginated_events_response(request, events, user=None):
    page_size = min(positive_int(request.GET.get('page_size'), DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
    page_number = positive_int(request.GET.get('page'), 1)
    paginator = Paginator(events, page_size)

    try:
        page = paginator.page(page_number)
    except EmptyPage:
        page = paginator.page(paginator.num_pages or 1)

    def page_url(target_page):
        params = request.GET.copy()
        params['page'] = target_page
        return request.build_absolute_uri(f'{request.path}?{params.urlencode()}')

    payload = [event_payload(event, request=request, user=user) for event in page.object_list]
    return JsonResponse(
        {
            'count': paginator.count,
            'next': page_url(page.next_page_number()) if page.has_next() else None,
            'previous': page_url(page.previous_page_number()) if page.has_previous() else None,
            'results': payload,
        }
    )


def validation_response(errors):
    return JsonResponse(errors, status=400)


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


def apply_event_data(event, data, partial=False):
    errors = {}
    for field in EVENT_FIELDS:
        value = data.get(field)
        if value in (None, ''):
            if not partial and field not in OPTIONAL_EVENT_FIELDS:
                errors[field] = ['This field is required.']
            elif field in data:
                setattr(event, field, '')
            continue
        if field == 'date':
            try:
                value = parse_event_datetime(value)
            except ValueError as exc:
                errors[field] = [str(exc)]
                continue
        if field == 'category' and not Category.objects.filter(slug=value, is_active=True).exists():
            errors[field] = ['Select a valid category.']
            continue
        setattr(event, field, value)
    return errors


def categories_collection(request):
    error = require_methods(request, ['GET'])
    if error:
        return error

    categories = Category.objects.filter(is_active=True)
    payload = [category_payload(category) for category in categories]
    return JsonResponse(payload, safe=False)


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
        return validation_response({'email': ['A user with this email already exists.']})

    token = AuthToken.create_for_user(user)
    return JsonResponse({'key': token.key})


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

    token = AuthToken.create_for_user(user)
    return JsonResponse({'key': token.key})


@csrf_exempt
def logout(request):
    error = require_methods(request, ['POST'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    header = request.headers.get('Authorization', '')
    key = header.split(' ', 1)[1].strip()
    AuthToken.objects.filter(user=user, key=key).delete()
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

    writable = set(USER_FIELDS) - {'id', 'email'}
    for field in writable:
        if field in data:
            setattr(user, field, data[field])
    user.save()
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
    return JsonResponse({'detail': 'Password reset email sent.'})


@csrf_exempt
def password_reset_confirm(request):
    error = require_methods(request, ['POST'])
    if error:
        return error
    return JsonResponse({'detail': 'Password reset complete.'})


@csrf_exempt
def events_collection(request):
    error = require_methods(request, ['GET', 'POST'])
    if error:
        return error

    user = authenticate_token(request)
    if request.method == 'GET':
        events = filtered_events(request.GET)
        return paginated_events_response(request, events, user=user)

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    data = parse_body(request)
    if data is None:
        return json_error('Invalid JSON.', status=400)

    event = Event(created_by=user)
    errors = apply_event_data(event, data, partial=False)
    if errors:
        return validation_response(errors)
    if request.FILES.get('image'):
        event.image = request.FILES['image']
    event.save()
    return JsonResponse(event_payload(event, request=request, user=user), status=201)


@csrf_exempt
def event_detail(request, event_id):
    error = require_methods(request, ['GET', 'PUT', 'DELETE'])
    if error:
        return error

    event = get_object_or_404(Event, id=event_id)
    user = authenticate_token(request)

    if request.method == 'GET':
        return JsonResponse(event_payload(event, request=request, user=user))

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error
    if event.created_by_id != user.id and not user.is_staff:
        return json_error('You do not have permission to modify this event.', status=403)

    if request.method == 'DELETE':
        event.delete()
        return JsonResponse({'detail': 'Event deleted successfully.'})

    data = parse_body(request)
    if data is None:
        return json_error('Invalid JSON.', status=400)

    errors = apply_event_data(event, data, partial=True)
    if errors:
        return validation_response(errors)
    if request.FILES.get('image'):
        event.image = request.FILES['image']
    event.save()
    return JsonResponse(event_payload(event, request=request, user=user))


@csrf_exempt
def toggle_like(request, event_id):
    error = require_methods(request, ['POST'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    event = get_object_or_404(Event, id=event_id)
    like, created = EventLike.objects.get_or_create(user=user, event=event)
    if created:
        return JsonResponse({'message': 'Event liked successfully.', 'liked': True})
    like.delete()
    return JsonResponse({'message': 'Event unliked successfully.', 'liked': False})


@csrf_exempt
def toggle_save(request, event_id):
    error = require_methods(request, ['POST'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    event = get_object_or_404(Event, id=event_id)
    save, created = EventSave.objects.get_or_create(user=user, event=event)
    if created:
        return JsonResponse({'message': 'Event saved successfully.', 'saved': True})
    save.delete()
    return JsonResponse({'message': 'Event unsaved successfully.', 'saved': False})


def liked_events(request):
    error = require_methods(request, ['GET'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    events = Event.objects.filter(likes__user=user).select_related('created_by')
    payload = [event_payload(event, request=request, user=user) for event in events]
    return JsonResponse(payload, safe=False)


def saved_events(request):
    error = require_methods(request, ['GET'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    events = Event.objects.filter(saves__user=user).select_related('created_by')
    payload = [event_payload(event, request=request, user=user) for event in events]
    return JsonResponse(payload, safe=False)


def my_events(request):
    error = require_methods(request, ['GET'])
    if error:
        return error

    user, auth_error = require_auth(request)
    if auth_error:
        return auth_error

    events = Event.objects.filter(created_by=user).select_related('created_by')
    payload = [event_payload(event, request=request, user=user) for event in events]
    return JsonResponse(payload, safe=False)
