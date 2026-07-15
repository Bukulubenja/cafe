from datetime import date

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.reports.services import build_balance_sheet_data

from .decorators import roles_required
from .roles import MANAGER_ROLES
from .utils import resolve_branch


@roles_required(*MANAGER_ROLES)
def balance_sheet(request):
    branch = resolve_branch(request)
    today = timezone.localdate()
    start_param = request.GET.get("period_start")
    end_param = request.GET.get("period_end")
    try:
        period_start = date.fromisoformat(start_param) if start_param else today.replace(day=1)
        period_end = date.fromisoformat(end_param) if end_param else today
    except ValueError:
        messages.error(request, "Invalid date; showing this month instead.")
        period_start, period_end = today.replace(day=1), today

    if period_start > period_end:
        messages.error(request, "Period start must not be after period end; showing this month instead.")
        period_start, period_end = today.replace(day=1), today

    data = build_balance_sheet_data(period_start, period_end) if branch else None
    return render(request, "web/balance_sheet.html", {"branch": branch, "data": data})
