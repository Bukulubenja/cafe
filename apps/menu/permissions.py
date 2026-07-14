from apps.accounts.models import User
from apps.accounts.permissions import RolePermission


class MenuPermission(RolePermission):
    """Owner/Manager can manage the menu; Owner/Manager/Waiter/Cashier can
    read it (to explain items/prices to customers). Chef has no access here
    -- kitchen tickets are served through the pos app without price data.
    """

    read_roles = (User.Role.OWNER, User.Role.MANAGER, User.Role.WAITER, User.Role.CASHIER)
    write_roles = (User.Role.OWNER, User.Role.MANAGER)
