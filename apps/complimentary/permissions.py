from apps.accounts.models import User
from apps.accounts.permissions import RolePermission


class ComplimentaryMealPermission(RolePermission):
    """Any staff member can file a complimentary meal request (readme's
    examples span every role: manager lunch, waiter breakfast, chef tea...);
    approval is gated separately by IsManagerOrAbove.
    """

    read_roles = write_roles = (
        User.Role.OWNER,
        User.Role.MANAGER,
        User.Role.WAITER,
        User.Role.CHEF,
        User.Role.CASHIER,
    )
