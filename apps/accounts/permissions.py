from rest_framework.permissions import BasePermission

from .models import User


class HasRole(BasePermission):
    """DRF permission factory: HasRole(User.Role.MANAGER, User.Role.OWNER)."""

    def __init__(self, *roles):
        self.roles = roles

    def __call__(self):
        return self

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_superuser or user.role in self.roles)
        )


class IsOwner(HasRole):
    def __init__(self):
        super().__init__(User.Role.OWNER)


class IsManagerOrAbove(HasRole):
    def __init__(self):
        super().__init__(User.Role.OWNER, User.Role.MANAGER)
