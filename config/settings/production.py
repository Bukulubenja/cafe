from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if not ALLOWED_HOSTS:  # noqa: F405
    raise RuntimeError("DJANGO_ALLOWED_HOSTS must be set in production")

if SECRET_KEY.startswith("django-insecure-"):  # noqa: F405
    raise RuntimeError("DJANGO_SECRET_KEY must be set to a real secret in production")

# The in-memory channel layer only works within a single process -- in
# production there are multiple worker processes, so a real (Redis) layer
# is required or kitchen broadcasts would silently only reach whichever
# worker happened to handle that request.
REDIS_URL = env("REDIS_URL")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL must be set in production for the Channels layer")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}
