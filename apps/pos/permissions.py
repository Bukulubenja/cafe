from apps.accounts.models import User
from apps.accounts.permissions import RolePermission


class TablePermission(RolePermission):
    """Anyone on staff can see the table map; only Owner/Manager set up tables."""

    read_roles = (User.Role.OWNER, User.Role.MANAGER, User.Role.WAITER, User.Role.CASHIER, User.Role.CHEF)
    write_roles = (User.Role.OWNER, User.Role.MANAGER)


class OrderPermission(RolePermission):
    """Owner/Manager/Waiter create and edit orders; Cashier can view them."""

    read_roles = (User.Role.OWNER, User.Role.MANAGER, User.Role.WAITER, User.Role.CASHIER)
    write_roles = (User.Role.OWNER, User.Role.MANAGER, User.Role.WAITER)


class CanTakePayment(RolePermission):
    """Both Waiter and Cashier can receive payment, per the readme's role list.

    Only ever used on the (POST-only) `pay` action, so `write_roles` is what
    gets checked regardless of method.
    """

    write_roles = (User.Role.OWNER, User.Role.MANAGER, User.Role.WAITER, User.Role.CASHIER)


class KitchenPermission(RolePermission):
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
