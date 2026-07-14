from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.models import AuditLog
from apps.inventory.services import deduct_stock_for_order_item

from .models import LoyaltyTransaction

# readme: "Every 50,000 UGX -> Earn points". One point per complete 50,000
# UGX spent on a single paid order.
POINTS_EARN_THRESHOLD = Decimal("50000")


def award_points_for_order(order):
    """Award loyalty points for a paid order, if it's linked to a customer.
    A no-op for walk-in/unidentified customers or orders under the threshold.
    """
    if order.customer_id is None:
        return

    points = int(order.total // POINTS_EARN_THRESHOLD)
    if points <= 0:
        return

    LoyaltyTransaction.objects.create(
        customer=order.customer,
        transaction_type=LoyaltyTransaction.Type.EARN,
        points=points,
        order=order,
        tenant=order.tenant,
        branch=order.branch,
    )


class _RedemptionItem:
    """Adapts a redemption to the shape deduct_stock_for_order_item expects
    (menu_item/quantity/branch/tenant) without depending on apps.pos."""

    def __init__(self, menu_item, branch):
        self.menu_item = menu_item
        self.quantity = 1
        self.branch = branch
        self.tenant = branch.tenant


@transaction.atomic
def redeem_points(customer, menu_item, branch, actor=None):
    """Redeem one unit of `menu_item` for `customer`'s loyalty points.

    Validates the item is redeemable and the customer has enough points,
    deducts the item's recipe ingredients from branch stock (same as a real
    sale), and records the spend as a ledger entry.
    """
    if menu_item.points_cost is None:
        raise ValidationError(f"{menu_item.name} is not redeemable for points.")
    if customer.loyalty_points_balance < menu_item.points_cost:
        raise ValidationError("Customer does not have enough points to redeem this item.")

    deduct_stock_for_order_item(_RedemptionItem(menu_item, branch))

    transaction_record = LoyaltyTransaction.objects.create(
        customer=customer,
        transaction_type=LoyaltyTransaction.Type.REDEEM,
        points=menu_item.points_cost,
        menu_item=menu_item,
        created_by=actor,
        tenant=branch.tenant,
        branch=branch,
    )
    AuditLog.objects.create(
        tenant=branch.tenant,
        branch=branch,
        actor=actor,
        action="loyalty.redeemed",
        object_repr=f"{customer} redeemed {menu_item.name}",
    )
    return transaction_record
