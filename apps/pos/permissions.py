from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import User


class _RolePermission(BasePermission):
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


class TablePermission(_RolePermission):
    """Anyone on staff can see the table map; only Owner/Manager set up tables."""

    read_roles = (User.Role.OWNER, User.Role.MANAGER, User.Role.WAITER, User.Role.CASHIER, User.Role.CHEF)
    write_roles = (User.Role.OWNER, User.Role.MANAGER)


class OrderPermission(_RolePermission):
    """Owner/Manager/Waiter create and edit orders; Cashier can view/pay them."""

    read_roles = (User.Role.OWNER, User.Role.MANAGER, User.Role.WAITER, User.Role.CASHIER)
    write_roles = (User.Role.OWNER, User.Role.MANAGER, User.Role.WAITER)


class CanTakePayment(_RolePermission):
    """Both Waiter and Cashier can receive payment, per the readme's role list."""

    write_roles = (User.Role.OWNER, User.Role.MANAGER, User.Role.WAITER, User.Role.CASHIER)

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        return user.role in self.write_roles


class KitchenPermission(_RolePermission):
    """Chef (and Owner/Manager for oversight) drive kitchen ticket status;
    Waiter/Cashier can read the queue to know when food is ready."""

    read_roles = (
        User.Role.OWNER,
        User.Role.MANAGER,
        User.Role.CHEF,
        User.Role.WAITER,
        User.Role.CASHIER,
    )
    write_roles = (User.Role.OWNER, User.Role.MANAGER, User.Role.CHEF)
