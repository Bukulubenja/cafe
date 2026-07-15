from datetime import date

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.reports.services import build_balance_sheet_data, build_leaderboards

from .decorators import roles_required
from .roles import MANAGER_ROLES
from .utils import csv_response, resolve_branch


def _resolve_period(request):
    """period_start/period_end query params, defaulting to month-to-date;
    falls back to that default (with a user-facing message) on anything
    invalid, rather than erroring the whole page.
    """
    today = timezone.localdate()
    start_param = request.GET.get("period_start")
    end_param = request.GET.get("period_end")
    try:
        period_start = date.fromisoformat(start_param) if start_param else today.replace(day=1)
        period_end = date.fromisoformat(end_param) if end_param else today
    except ValueError:
        messages.error(request, "Invalid date; showing this month instead.")
        return today.replace(day=1), today

    if period_start > period_end:
        messages.error(request, "Period start must not be after period end; showing this month instead.")
        return today.replace(day=1), today

    return period_start, period_end


@roles_required(*MANAGER_ROLES)
def balance_sheet(request):
    branch = resolve_branch(request)
    period_start, period_end = _resolve_period(request)
    data = build_balance_sheet_data(period_start, period_end) if branch else None
    return render(request, "web/balance_sheet.html", {"branch": branch, "data": data})


@roles_required(*MANAGER_ROLES)
def balance_sheet_download(request):
    branch = resolve_branch(request)
    period_start, period_end = _resolve_period(request)
    if branch is None:
        messages.error(request, "This café has no branches configured yet.")
        return redirect("web:balance_sheet")

    data = build_balance_sheet_data(period_start, period_end)
    rows = [
        ("Period", f"{period_start} to {period_end}"),
        (),
        ("Income statement", ""),
        ("Sales", data["income"]["sales"]),
        ("Cost of goods sold", -data["income"]["cogs"]),
        ("Gross profit", data["income"]["gross_profit"]),
    ]
    for category, amount in data["income"]["expenses_by_category"].items():
        rows.append((category, -amount))
    rows += [
        ("Payroll", -data["income"]["payroll"]),
        ("Purchases (cash flow only, not a P&L cost)", data["income"]["purchases"]),
        ("Net profit", data["income"]["net_profit"]),
        (),
        ("Assets, liabilities & equity", ""),
        ("Inventory value", data["assets"]["inventory_value"]),
        ("Cash on hand (latest closing)", data["assets"]["cash_on_hand"]),
        ("Total assets", data["assets"]["total"]),
        ("Accounts payable (owed to suppliers)", data["liabilities"]["accounts_payable"]),
        ("Total liabilities", data["liabilities"]["total"]),
        ("Owner equity", data["owner_equity"]),
    ]
    filename = f"balance-sheet_{period_start}_{period_end}.csv"
    return csv_response(filename, ("Line", "Amount (UGX)"), rows)


@roles_required(*MANAGER_ROLES)
def leaderboards(request):
    branch = resolve_branch(request)
    try:
        window_days = int(request.GET.get("window_days", 30))
        if window_days <= 0:
            raise ValueError
    except ValueError:
        messages.error(request, "Invalid window; showing the last 30 days instead.")
        window_days = 30

    data = build_leaderboards(window_days) if branch else None
    return render(request, "web/leaderboards.html", {"branch": branch, "data": data})
