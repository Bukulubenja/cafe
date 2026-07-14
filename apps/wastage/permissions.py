from apps.accounts.models import User
from apps.accounts.permissions import RolePermission


class WastagePermission(RolePermission):
    """Owner/Manager/Chef can record and view wastage; approval is gated
    separately by IsManagerOrAbove on the approve/reject actions.
    """

    read_roles = (User.Role.OWNER, User.Role.MANAGER, User.Role.CHEF)
    write_roles = (User.Role.OWNER, User.Role.MANAGER, User.Role.CHEF)
