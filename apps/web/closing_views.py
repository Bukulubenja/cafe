from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.closing.models import DailyClosing

from .decorators import roles_required
from .roles import MANAGER_ROLES
from .utils import friendly_error, resolve_branch


@roles_required(*MANAGER_ROLES)
def closing_list(request):
    branch = resolve_branch(request)
    today = timezone.localdate()
    already_closed_today = DailyClosing.objects.filter(branch=branch, date=today).exists() if branch else False

    if request.method == "POST":
        if branch is None:
            messages.error(request, "This café has no branches configured yet.")
            return redirect("web:closing_list")
        try:
            cash_counted = Decimal(request.POST.get("cash_counted", "0"))
            closing = DailyClosing.close_day(
                branch, cash_counted, actor=request.user, reason=request.POST.get("reason", "")
            )
        except (DjangoValidationError, InvalidOperation) as exc:
            messages.error(request, friendly_error(exc) if isinstance(exc, DjangoValidationError) else "Invalid cash amount.")
        else:
            messages.success(request, f"Closed {closing.date}: difference {closing.difference} UGX.")
        return redirect("web:closing_list")

    closings = DailyClosing.objects.select_related("closed_by") if branch else DailyClosing.objects.none()
    return render(
        request,
        "web/closing_list.html",
        {"branch": branch, "closings": closings, "already_closed_today": already_closed_today, "today": today},
    )
