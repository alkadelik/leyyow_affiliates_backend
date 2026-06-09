from decouple import config

env = config('DJANGO_ENV', default='local')

if env == 'production':
    from .production import *
else:
    from .local import *
