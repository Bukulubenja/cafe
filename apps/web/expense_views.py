from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.expenses.models import Expense

from .decorators import roles_required
from .roles import MANAGER_ROLES
from .utils import friendly_error, resolve_branch


@roles_required(*MANAGER_ROLES)
def expense_list(request):
    branch = resolve_branch(request)
    if request.method == "POST":
        if branch is None:
            messages.error(request, "This café has no branches configured yet.")
            return redirect("web:expense_list")
        expense = Expense(
            tenant=branch.tenant,
            branch=branch,
            category=request.POST.get("category", Expense.Category.OTHER),
            date=request.POST.get("date") or timezone.localdate(),
            notes=request.POST.get("notes", ""),
            recorded_by=request.user,
        )
        try:
            expense.amount = request.POST.get("amount") or 0
            expense.full_clean()
            expense.save()
        except DjangoValidationError as exc:
            messages.error(request, friendly_error(exc))
        else:
            messages.success(request, f"Recorded {expense}.")
        return redirect("web:expense_list")

    expenses = Expense.objects.select_related("recorded_by") if branch else Expense.objects.none()
    total = sum((e.amount for e in expenses), Decimal("0.00"))
    return render(
        request,
        "web/expense_list.html",
        {
            "branch": branch,
            "expenses": expenses,
            "total": total,
            "categories": Expense.Category.choices,
        },
    )
