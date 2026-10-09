from django.conf import settings
from knox.auth import TokenAuthentication


class CookieTokenAuthentication(TokenAuthentication):
    """Knox token auth that also accepts the token from an httpOnly cookie.

    The `Authorization: Token <token>` header still works (used by the test
    suite and any non-browser client). The web frontend relies on the cookie
    instead, since page JavaScript can't read or exfiltrate an httpOnly cookie
    the way it could a token sitting in localStorage.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            return result

        token = request.COOKIES.get(settings.AUTH_COOKIE_NAME)
        if not token:
            return None
        return self.authenticate_credentials(token.encode('utf-8'))
