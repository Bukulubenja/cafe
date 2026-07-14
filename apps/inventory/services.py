from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.models import AuditLog

from .models import StockItem


@transaction.atomic
def deduct_stock_for_order_item(order_item):
    """Deduct an OrderItem's recipe ingredients from its branch's stock.

    All-or-nothing: if any ingredient is short, nothing is deducted and a
    ValidationError listing the shortfall(s) is raised. A no-op if the menu
    item has no recipe configured yet.
    """
    recipe_items = list(order_item.menu_item.recipe_items.select_related("ingredient"))
    if not recipe_items:
        return

    branch = order_item.branch
    shortfalls = []
    to_deduct = []
    for recipe_item in recipe_items:
        required = recipe_item.quantity_required * order_item.quantity
        stock_item = (
            StockItem.unscoped.select_for_update()
            .filter(branch=branch, ingredient=recipe_item.ingredient)
            .first()
        )
        if stock_item is None or stock_item.quantity_on_hand < required:
            shortfalls.append(recipe_item.ingredient.name)
            continue
        to_deduct.append((stock_item, required))

    if shortfalls:
        raise ValidationError(f"Insufficient stock for: {', '.join(shortfalls)}")

    for stock_item, required in to_deduct:
        stock_item.quantity_on_hand -= required
        stock_item.save(update_fields=["quantity_on_hand", "updated_at"])

    AuditLog.objects.create(
        tenant=order_item.tenant,
        branch=branch,
        action="stock.deducted",
        object_repr=f"{order_item.menu_item.name} x{order_item.quantity}",
    )
