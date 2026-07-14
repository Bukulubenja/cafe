from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def roles_required(*roles):
    """Same role-gating as this project's DRF RolePermission classes, for
    plain Django views. Requires login first (redirects to web:login)."""

    def decorator(view_func):
        @wraps(view_func)
        @login_required(login_url="web:login")
        def wrapped(request, *args, **kwargs):
            if not (request.user.is_superuser or request.user.role in roles):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
