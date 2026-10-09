from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Tags, Warning, register


def _is_local(url):
    return (urlparse(url).hostname or '') in {'localhost', '127.0.0.1', '0.0.0.0', ''}


@register(Tags.security, deploy=True)
def production_configuration(app_configs, **kwargs):
    """Flag settings that pass Django's own checks but break a real
    deployment of the separate frontend + API setup."""
    if settings.DEBUG:
        return []
    warnings = []
    if _is_local(settings.FRONTEND_URL):
        warnings.append(Warning(
            'FRONTEND_URL points at localhost; links in emails (password reset, event pages) will be broken.',
            hint='Set FRONTEND_URL to the deployed frontend origin.', id='eventlight.W001',
        ))
    if not settings.CORS_ALLOWED_ORIGINS or all(_is_local(origin) for origin in settings.CORS_ALLOWED_ORIGINS):
        warnings.append(Warning(
            'CORS_ALLOWED_ORIGINS only allows localhost; the deployed frontend cannot call the API.',
            hint='Set CORS_ALLOWED_ORIGINS to the deployed frontend origin.', id='eventlight.W002',
        ))
    missing_csrf = sorted(set(settings.CORS_ALLOWED_ORIGINS) - set(settings.CSRF_TRUSTED_ORIGINS))
    if missing_csrf:
        warnings.append(Warning(
            f'Origins allowed by CORS but not trusted for CSRF: {", ".join(missing_csrf)}. '
            'Every POST/PATCH/DELETE from them will fail with 403.',
            hint='Add them to CSRF_TRUSTED_ORIGINS.', id='eventlight.W003',
        ))
    if not settings.CLOUDINARY_URL:
        warnings.append(Warning(
            'CLOUDINARY_URL is not set: uploaded event images go to local disk, which is not served when '
            'DEBUG is false and is lost on redeploy on most hosts.',
            hint='Set CLOUDINARY_URL in production.', id='eventlight.W004',
        ))
    if not settings.ZEPTOMAIL_API_KEY:
        warnings.append(Warning(
            'ZEPTOMAIL_API_KEY is not set; password reset and notification emails will not be sent.',
            id='eventlight.W005',
        ))
    return warnings
