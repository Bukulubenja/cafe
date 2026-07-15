from apps.accounts.models import User
from apps.accounts.permissions import RolePermission


class ShiftPermission(RolePermission):
    """Every staff role clocks their own shift in/out; force-closing
    someone else's shift is gated separately by IsManagerOrAbove.
    """

    read_roles = write_roles = (
        User.Role.OWNER,
        User.Role.MANAGER,
        User.Role.WAITER,
        User.Role.CHEF,
        User.Role.CASHIER,
    )
