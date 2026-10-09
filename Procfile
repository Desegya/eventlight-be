release: python manage.py migrate --noinput && python manage.py createcachetable
web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --timeout 30 --log-file -
