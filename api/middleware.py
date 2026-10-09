import contextvars
import logging
import re
import uuid

import sentry_sdk

_request_id = contextvars.ContextVar('request_id', default='-')
# Accept a caller-supplied ID (e.g. from a proxy) only if it is short and
# log-safe; anything else is replaced so it cannot inject into log lines.
_VALID_REQUEST_ID = re.compile(r'^[A-Za-z0-9._-]{1,64}$')


def current_request_id():
    return _request_id.get()


class RequestIdMiddleware:
    """Tags each request with an ID that is returned in X-Request-ID, added
    to every log line and Sentry event, and shown in 500 responses, so a
    user-reported error can be matched to the server-side logs."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.META.get('HTTP_X_REQUEST_ID', '')
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        request.request_id = request_id
        token = _request_id.set(request_id)
        sentry_sdk.set_tag('request_id', request_id)
        try:
            response = self.get_response(request)
        finally:
            _request_id.reset(token)
        response['X-Request-ID'] = request_id
        return response


class RequestIdLogFilter(logging.Filter):
    def filter(self, record):
        record.request_id = _request_id.get()
        return True
