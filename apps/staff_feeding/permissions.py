from apps.accounts.models import User
from apps.accounts.permissions import RolePermission


class FeedingRecordPermission(RolePermission):
    """Every staff role logs their own feeding record; the view further
    restricts reads to "my records only" for non-Owner/Manager roles.
    """

    read_roles = write_roles = (
        User.Role.OWNER,
        User.Role.MANAGER,
        User.Role.WAITER,
        User.Role.CHEF,
        User.Role.CASHIER,
    )
