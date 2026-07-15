from collections import defaultdict
from decimal import Decimal

from django.utils import timezone

from apps.complimentary.models import ComplimentaryMeal
from apps.expenses.models import Expense
from apps.inventory.models import StockItem
from apps.pos.models import Order, Table
from apps.wastage.models import WastageRecord


def build_dashboard_data():
    """Today's snapshot for the current tenant/branch context (readme's
    Dashboard module). Shared by the DRF DashboardView and the web
    dashboard template view so the two never drift apart.
    """
    today = timezone.localdate()

    orders_today = Order.objects.filter(status=Order.Status.PAID, closed_at__date=today)
    sales_today = Decimal("0.00")
    cogs_today = Decimal("0.00")
    item_counts = defaultdict(int)
    for order in orders_today.prefetch_related("items__menu_item"):
        sales_today += order.total
        for item in order.active_items:
            cogs_today += item.menu_item.cost_price * item.quantity
            item_counts[item.menu_item.name] += item.quantity

    expenses_today = sum((e.amount for e in Expense.objects.filter(date=today)), Decimal("0.00"))
    profit_today = sales_today - cogs_today - expenses_today

    low_stock_alerts = [
        {
            "ingredient": s.ingredient.name,
            "quantity_on_hand": s.quantity_on_hand,
            "minimum_quantity": s.minimum_quantity,
        }
        for s in StockItem.objects.select_related("ingredient").all()
        if s.is_low_stock
    ]

    top_items = sorted(item_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]

    comp_today = ComplimentaryMeal.objects.filter(status=ComplimentaryMeal.Status.APPROVED, approved_at__date=today)
    comp_cost_today = sum((m.total_cost or Decimal("0.00") for m in comp_today), Decimal("0.00"))

    return {
        "date": today,
        "sales_today": sales_today,
        "orders_today": orders_today.count(),
        "profit_today": profit_today,
        "expenses_today": expenses_today,
        "low_stock_alerts": low_stock_alerts,
        "busy_tables": Table.objects.filter(status=Table.Status.OCCUPIED).count(),
        "available_tables": Table.objects.filter(status=Table.Status.AVAILABLE).count(),
        "top_selling_items_today": [{"menu_item": name, "quantity_sold": qty} for name, qty in top_items],
        "complimentary_meals_today": {"count": comp_today.count(), "cost": comp_cost_today},
        "wastage_records_today": WastageRecord.objects.filter(created_at__date=today).count(),
    }
