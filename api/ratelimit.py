import json

from django.conf import settings


def client_ip(request):
    """Client IP for rate limiting.

    Behind a hosting proxy REMOTE_ADDR is the proxy itself, so keying on it
    would put every user in one shared bucket. Each trusted proxy appends the
    address it received the request from to X-Forwarded-For, so the entry
    NUM_TRUSTED_PROXIES from the right is the first one a client cannot forge.
    """
    proxies = settings.NUM_TRUSTED_PROXIES
    if proxies:
        forwarded = [part.strip() for part in request.META.get('HTTP_X_FORWARDED_FOR', '').split(',') if part.strip()]
        if len(forwarded) >= proxies:
            return forwarded[-proxies]
    return request.META.get('REMOTE_ADDR', '')


def email_key(_group, request):
    """Rate-limit key on the target account, so spreading guesses or reset
    emails across many IPs cannot get around the per-IP limit."""
    try:
        data = json.loads(request.body or b'{}')
    except (ValueError, UnicodeDecodeError):
        return ''
    if not isinstance(data, dict):
        return ''
    return str(data.get('email') or '').strip().lower()
