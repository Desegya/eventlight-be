"""
Middleware for cookie-based token authentication.

The auth token is stored in an httponly, SameSite=Lax cookie so the browser
never exposes it to JavaScript (preventing XSS token theft). This middleware
reads the cookie and injects it as the Authorization header so the existing
Knox TokenAuthentication can authenticate the request without modification.

The Authorization header is still supported as the primary auth method for
non-browser clients (mobile apps, CLI tools, etc.).
"""
from django.conf import settings


AUTH_COOKIE_NAME = getattr(settings, 'AUTH_COOKIE_NAME', 'auth_token')


class CookieTokenAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        cookie_token = request.COOKIES.get(AUTH_COOKIE_NAME)
        header = request.META.get('HTTP_AUTHORIZATION', '')
        if cookie_token and not header:
            request.META['HTTP_AUTHORIZATION'] = f'Token {cookie_token}'
        return self.get_response(request)


def set_auth_cookie(response, token):
    """Attach the auth token as an httponly cookie to a response."""
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=30 * 24 * 60 * 60,  # 30 days, matches REST_KNOX TOKEN_TTL
        httponly=True,
        secure=not settings.DEBUG,
        samesite='Lax',
        path='/',
    )


def clear_auth_cookie(response):
    """Remove the auth token cookie from a response."""
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path='/',
        samesite='Lax',
    )
