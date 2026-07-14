from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import User


class RolePermission(BasePermission):
    """Base for role-gated DRF permissions: authenticated staff whose `role`
    is in `read_roles` may use safe methods, `write_roles` for the rest.
    Superusers (platform admins) always pass.
    """

    read_roles = ()
    write_roles = ()

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        allowed = self.read_roles if request.method in SAFE_METHODS else self.write_roles
        return user.role in allowed


class IsManagerOrAbove(RolePermission):
    """Owner/Manager only. Meant for approval-type actions (approving
    wastage, complimentary meals, refunds, etc.) that are always POST, so
    only `write_roles` ever gets checked in practice.
    """

    read_roles = write_roles = (User.Role.OWNER, User.Role.MANAGER)
