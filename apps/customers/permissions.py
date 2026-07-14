from apps.accounts.models import User
from apps.accounts.permissions import RolePermission


class CustomerPermission(RolePermission):
    """Front-of-house staff (not Chef) look up, create, and manage customer
    records and process redemptions; Chef has no need for this.
    """

    read_roles = write_roles = (
        User.Role.OWNER,
        User.Role.MANAGER,
        User.Role.WAITER,
        User.Role.CASHIER,
    )
