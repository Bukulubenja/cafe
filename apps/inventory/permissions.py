from apps.accounts.models import User
from apps.accounts.permissions import RolePermission


class InventoryPermission(RolePermission):
    """Stock is a back-office concern: Owner can view it, Manager manages it
    (readme: Owner 'View stock', Manager 'Manage stock' / 'Approve stock
    adjustments'). Other roles have no access here.
    """

    read_roles = (User.Role.OWNER, User.Role.MANAGER)
    write_roles = (User.Role.OWNER, User.Role.MANAGER)
