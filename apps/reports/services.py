from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.closing.models import DailyClosing
from apps.complimentary.models import ComplimentaryMeal
from apps.core.context import get_current_branch
from apps.expenses.models import Expense
from apps.inventory.models import StockItem
from apps.menu.models import MenuItem
from apps.payroll.models import PayrollRun
from apps.pos.models import Order, OrderItem, Table
from apps.purchasing.models import PurchaseOrder, Supplier
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
        "recipe_cost_alerts": build_recipe_cost_alerts(),
        "wastage_records_today": WastageRecord.objects.filter(created_at__date=today).count(),
    }


def build_recipe_cost_alerts():
    """readme's Automatic Recipe Costing differentiator: menu items whose
    live recipe cost (today's branch ingredient buying prices) has drifted
    above the manually-set `cost_price`, silently eating into the margin
    someone assumed when they priced the item. Requires an ambient branch
    (set by TenantMiddleware) since recipe cost is priced per branch;
    returns [] with no branch in context.
    """
    branch = get_current_branch()
    if branch is None:
        return []

    alerts = []
    for item in MenuItem.objects.filter(is_available=True).prefetch_related("recipe_items__ingredient"):
        live_cost = item.recipe_cost_at(branch)
        if live_cost is not None and live_cost > item.cost_price:
            alerts.append(
                {
                    "menu_item": item.name,
                    "assumed_cost": item.cost_price,
                    "actual_cost": live_cost,
                    "assumed_margin": item.selling_price - item.cost_price,
                    "actual_margin": item.selling_price - live_cost,
                }
            )
    return alerts


def build_balance_sheet_data(period_start, period_end):
    """readme's Balance Sheet: an income statement for [period_start,
    period_end] plus a point-in-time assets/liabilities/equity snapshot.

    This isn't full double-entry bookkeeping -- there's no general ledger in
    this system -- so Assets/Liabilities/Equity are necessarily approximate:
    Assets = current inventory value (on-hand qty * buying price) + the most
    recent Daily Closing's counted cash (the only actual cash-count this
    system performs); Liabilities = total owed across all suppliers; Owner
    Equity is the standard plug (Assets - Liabilities), not a tracked figure.
    """
    orders = Order.objects.filter(
        status=Order.Status.PAID, closed_at__date__gte=period_start, closed_at__date__lte=period_end
    ).prefetch_related("items__menu_item")
    sales = Decimal("0.00")
    cogs = Decimal("0.00")
    for order in orders:
        sales += order.total
        for item in order.active_items:
            cogs += item.menu_item.cost_price * item.quantity
    gross_profit = sales - cogs

    expenses_by_category = defaultdict(lambda: Decimal("0.00"))
    for expense in Expense.objects.filter(date__gte=period_start, date__lte=period_end):
        expenses_by_category[expense.get_category_display()] += expense.amount
    total_expenses = sum(expenses_by_category.values(), Decimal("0.00"))

    purchases_total = sum(
        (
            po.total
            for po in PurchaseOrder.objects.filter(
                status=PurchaseOrder.Status.RECEIVED,
                approved_at__date__gte=period_start,
                approved_at__date__lte=period_end,
            )
        ),
        Decimal("0.00"),
    )

    payroll_total = sum(
        (
            run.total_paid
            for run in PayrollRun.objects.filter(period_start__gte=period_start, period_end__lte=period_end)
        ),
        Decimal("0.00"),
    )

    # Purchases replenish stock rather than being consumed, so they're shown
    # for cash-flow visibility but excluded from Net Profit -- COGS already
    # captures the cost of what was actually sold, and double-subtracting
    # the same stock via Purchases would understate profit.
    net_profit = gross_profit - total_expenses - payroll_total

    inventory_value = sum(
        (s.quantity_on_hand * s.buying_price for s in StockItem.objects.select_related("ingredient")),
        Decimal("0.00"),
    )
    latest_closing = DailyClosing.objects.order_by("-date").first()
    cash_on_hand = latest_closing.cash_counted if latest_closing else Decimal("0.00")
    assets = inventory_value + cash_on_hand

    liabilities = sum((supplier.balance for supplier in Supplier.objects.all()), Decimal("0.00"))
    owner_equity = assets - liabilities

    return {
        "period_start": period_start,
        "period_end": period_end,
        "income": {
            "sales": sales,
            "cogs": cogs,
            "gross_profit": gross_profit,
            "expenses_by_category": dict(expenses_by_category),
            "total_expenses": total_expenses,
            "purchases": purchases_total,
            "payroll": payroll_total,
            "net_profit": net_profit,
        },
        "assets": {
            "inventory_value": inventory_value,
            "cash_on_hand": cash_on_hand,
            "total": assets,
        },
        "liabilities": {
            "accounts_payable": liabilities,
            "total": liabilities,
        },
        "owner_equity": owner_equity,
    }


def build_leaderboards(window_days=30):
    """readme's Reports > Best waiter / Fastest chef, over a rolling
    window. Best waiter ranks by revenue from the paid orders they created
    (order count shown alongside as a secondary stat). Fastest chef ranks
    by average time from started-cooking to ready across the tickets they
    cooked -- only tickets with a recorded cooked_by count, so this stays
    empty until a chef has actually driven kitchen tickets through the API.
    """
    since = timezone.now() - timedelta(days=window_days)

    waiter_stats = defaultdict(lambda: {"orders": 0, "revenue": Decimal("0.00")})
    orders = Order.objects.filter(status=Order.Status.PAID, closed_at__gte=since).select_related("created_by")
    for order in orders:
        key = order.created_by.email if order.created_by else "unknown"
        waiter_stats[key]["orders"] += 1
        waiter_stats[key]["revenue"] += order.total
    best_waiters = sorted(
        ({"staff": staff, **stats} for staff, stats in waiter_stats.items()),
        key=lambda s: s["revenue"],
        reverse=True,
    )

    chef_stats = defaultdict(lambda: {"tickets": 0, "total_seconds": Decimal("0")})
    tickets = OrderItem.objects.filter(
        cooked_by__isnull=False, started_cooking_at__gte=since, ready_at__isnull=False
    ).select_related("cooked_by")
    for ticket in tickets:
        key = ticket.cooked_by.email
        chef_stats[key]["tickets"] += 1
        chef_stats[key]["total_seconds"] += Decimal((ticket.ready_at - ticket.started_cooking_at).total_seconds())
    fastest_chefs = sorted(
        (
            {
                "staff": staff,
                "tickets": stats["tickets"],
                "avg_minutes": round(stats["total_seconds"] / stats["tickets"] / 60, 1),
            }
            for staff, stats in chef_stats.items()
        ),
        key=lambda s: s["avg_minutes"],
    )

    return {"window_days": window_days, "best_waiters": best_waiters, "fastest_chefs": fastest_chefs}
