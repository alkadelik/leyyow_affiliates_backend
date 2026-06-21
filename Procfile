web: python manage.py collectstatic --noinput && python manage.py migrate && gunicorn affiliates_backend.wsgi:application --bind 0.0.0.0:$PORT
