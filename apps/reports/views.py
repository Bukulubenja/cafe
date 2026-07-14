from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsManagerOrAbove
from apps.complimentary.models import ComplimentaryMeal
from apps.expenses.models import Expense
from apps.inventory.models import StockItem
from apps.pos.models import Order, Table
from apps.wastage.models import WastageRecord

from .utils import bucket_key

PERIOD_WINDOW_DAYS = {"daily": 30, "weekly": 90, "monthly": 365}


def _validate_period(request):
    period = request.query_params.get("period", "daily")
    if period not in PERIOD_WINDOW_DAYS:
        raise DRFValidationError({"period": "Must be one of: daily, weekly, monthly."})
    return period


class DashboardView(APIView):
    """Today's snapshot for the acting user's café/branch (readme's
    Dashboard module). Owner with no branch pinned sees all branches
    combined; staff pinned to one branch see just that branch -- both for
    free, via the ambient tenant/branch scoping on the default managers.
    """

    permission_classes = [IsManagerOrAbove]

    def get(self, request):
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

        return Response(
            {
                "date": today.isoformat(),
                "sales_today": sales_today,
                "orders_today": orders_today.count(),
                "profit_today": profit_today,
                "expenses_today": expenses_today,
                "low_stock_alerts": low_stock_alerts,
                "busy_tables": Table.objects.filter(status=Table.Status.OCCUPIED).count(),
                "available_tables": Table.objects.filter(status=Table.Status.AVAILABLE).count(),
                "top_selling_items_today": [
                    {"menu_item": name, "quantity_sold": qty} for name, qty in top_items
                ],
                "complimentary_meals_today": {"count": comp_today.count(), "cost": comp_cost_today},
                "wastage_records_today": WastageRecord.objects.filter(created_at__date=today).count(),
            }
        )


class SalesReportView(APIView):
    """readme's Reports > Sales: Hourly/Daily/Weekly/Monthly. (Hourly isn't
    included here -- it's a same-day drill-down, not a historical trend --
    but daily/weekly/monthly buckets are.)
    """

    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        period = _validate_period(request)
        since = timezone.now() - timedelta(days=PERIOD_WINDOW_DAYS[period])

        buckets = defaultdict(lambda: {"orders": 0, "sales": Decimal("0.00")})
        orders = Order.objects.filter(status=Order.Status.PAID, closed_at__gte=since).prefetch_related(
            "items__menu_item"
        )
        for order in orders:
            key = bucket_key(order.closed_at, period)
            buckets[key]["orders"] += 1
            buckets[key]["sales"] += order.total

        results = [{"period": key, **buckets[key]} for key in sorted(buckets)]
        return Response({"period_type": period, "results": results})


class ProfitReportView(APIView):
    """readme's 'Daily Profit Instead of Daily Sales': revenue minus cost of
    goods sold minus operating expenses, bucketed the same as sales.
    """

    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        period = _validate_period(request)
        since = timezone.now() - timedelta(days=PERIOD_WINDOW_DAYS[period])

        buckets = defaultdict(lambda: {"revenue": Decimal("0.00"), "cogs": Decimal("0.00"), "expenses": Decimal("0.00")})

        orders = Order.objects.filter(status=Order.Status.PAID, closed_at__gte=since).prefetch_related(
            "items__menu_item"
        )
        for order in orders:
            key = bucket_key(order.closed_at, period)
            buckets[key]["revenue"] += order.total
            for item in order.active_items:
                buckets[key]["cogs"] += item.menu_item.cost_price * item.quantity

        for expense in Expense.objects.filter(date__gte=since.date()):
            buckets[bucket_key(expense.date, period)]["expenses"] += expense.amount

        results = []
        for key in sorted(buckets):
            b = buckets[key]
            results.append(
                {
                    "period": key,
                    "revenue": b["revenue"],
                    "cogs": b["cogs"],
                    "expenses": b["expenses"],
                    "net_profit": b["revenue"] - b["cogs"] - b["expenses"],
                }
            )
        return Response({"period_type": period, "results": results})


class LossDetectionView(APIView):
    """readme's Smart Loss Detection differentiator. Thresholds below are
    simple, documented defaults (not yet tenant-configurable) over a
    rolling 30-day window.
    """

    permission_classes = [IsManagerOrAbove]

    WINDOW_DAYS = 30
    EXCESSIVE_COMP_COUNT = 10
    EXCESSIVE_CANCEL_COUNT = 5
    LARGE_WASTAGE_QUANTITY = Decimal("10")

    def get(self, request):
        since = timezone.now() - timedelta(days=self.WINDOW_DAYS)

        comp_by_staff = defaultdict(lambda: {"count": 0, "cost": Decimal("0.00")})
        comp_meals = ComplimentaryMeal.objects.filter(
            status=ComplimentaryMeal.Status.APPROVED, approved_at__gte=since
        ).select_related("staff")
        for meal in comp_meals:
            key = meal.staff.email if meal.staff else "unknown"
            comp_by_staff[key]["count"] += 1
            comp_by_staff[key]["cost"] += meal.total_cost or Decimal("0.00")
        excessive_complimentary = [
            {"staff": staff, **stats}
            for staff, stats in comp_by_staff.items()
            if stats["count"] >= self.EXCESSIVE_COMP_COUNT
        ]

        cancels_by_staff = defaultdict(int)
        cancelled_orders = Order.objects.filter(status=Order.Status.CANCELLED, closed_at__gte=since).select_related(
            "created_by"
        )
        for order in cancelled_orders:
            key = order.created_by.email if order.created_by else "unknown"
            cancels_by_staff[key] += 1
        excessive_cancellations = [
            {"staff": staff, "cancelled_orders": count}
            for staff, count in cancels_by_staff.items()
            if count >= self.EXCESSIVE_CANCEL_COUNT
        ]

        wastage_by_ingredient = defaultdict(lambda: Decimal("0"))
        for record in WastageRecord.objects.filter(created_at__gte=since).select_related("ingredient"):
            wastage_by_ingredient[record.ingredient.name] += record.quantity
        excessive_wastage = [
            {"ingredient": name, "total_quantity": qty}
            for name, qty in wastage_by_ingredient.items()
            if qty >= self.LARGE_WASTAGE_QUANTITY
        ]

        return Response(
            {
                "window_days": self.WINDOW_DAYS,
                "excessive_complimentary_by_staff": excessive_complimentary,
                "excessive_cancellations_by_staff": excessive_cancellations,
                "excessive_wastage_by_ingredient": excessive_wastage,
            }
        )
