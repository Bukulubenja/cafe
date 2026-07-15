from apps.accounts.models import User

# Shared role tuples for apps.web's roles_required() decorator, kept in one
# place since every view module needs some subset of these -- importing
# them from views.py (a leaf module reused by nothing else) would make
# every new screen depend on the one file most likely to keep changing.
MANAGER_ROLES = (User.Role.OWNER, User.Role.MANAGER)
KITCHEN_STAFF_ROLES = (User.Role.OWNER, User.Role.MANAGER, User.Role.CHEF)
FRONT_OF_HOUSE_ROLES = (User.Role.OWNER, User.Role.MANAGER, User.Role.WAITER, User.Role.CASHIER)
ORDER_WRITE_ROLES = (User.Role.OWNER, User.Role.MANAGER, User.Role.WAITER)
PAYMENT_ROLES = (User.Role.OWNER, User.Role.MANAGER, User.Role.WAITER, User.Role.CASHIER)
KITCHEN_VIEW_ROLES = (User.Role.OWNER, User.Role.MANAGER, User.Role.CHEF, User.Role.WAITER, User.Role.CASHIER)
ALL_STAFF_ROLES = (
    User.Role.OWNER,
    User.Role.MANAGER,
    User.Role.WAITER,
    User.Role.CHEF,
    User.Role.CASHIER,
)
