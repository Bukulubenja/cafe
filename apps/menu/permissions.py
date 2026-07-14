from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import User


class MenuPermission(BasePermission):
    """Owner/Manager can manage the menu; Owner/Manager/Waiter/Cashier can
    read it (to explain items/prices to customers). Chef has no access here
    -- kitchen tickets are served through the pos app without price data.
    """

    read_roles = (User.Role.OWNER, User.Role.MANAGER, User.Role.WAITER, User.Role.CASHIER)
    write_roles = (User.Role.OWNER, User.Role.MANAGER)

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        allowed_roles = self.read_roles if request.method in SAFE_METHODS else self.write_roles
        return user.role in allowed_roles
