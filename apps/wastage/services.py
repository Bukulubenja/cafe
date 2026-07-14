from django.core.exceptions import ValidationError
from django.db import transaction

from apps.inventory.models import StockItem


@transaction.atomic
def apply_wastage(wastage_record):
    """Deduct a wastage record's quantity from its branch's stock.

    Raises ValidationError (leaving stock untouched) if there isn't enough
    of the ingredient on hand to account for the reported loss.
    """
    stock_item = (
        StockItem.unscoped.select_for_update()
        .filter(branch=wastage_record.branch, ingredient=wastage_record.ingredient)
        .first()
    )
    if stock_item is None or stock_item.quantity_on_hand < wastage_record.quantity:
        raise ValidationError(
            f"Insufficient stock on hand for {wastage_record.ingredient.name} to record this wastage."
        )
    stock_item.quantity_on_hand -= wastage_record.quantity
    stock_item.save(update_fields=["quantity_on_hand", "updated_at"])


@transaction.atomic
def reverse_wastage(wastage_record):
    """Restore a wastage record's quantity back to stock (used when a
    manager rejects a record as an incorrect/invalid report)."""
    stock_item = (
        StockItem.unscoped.select_for_update()
        .filter(branch=wastage_record.branch, ingredient=wastage_record.ingredient)
        .first()
    )
    if stock_item is not None:
        stock_item.quantity_on_hand += wastage_record.quantity
        stock_item.save(update_fields=["quantity_on_hand", "updated_at"])
