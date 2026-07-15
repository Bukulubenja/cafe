from django.contrib import messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.inventory.models import Ingredient
from apps.wastage.models import WastageRecord

from .decorators import roles_required
from .roles import KITCHEN_STAFF_ROLES, MANAGER_ROLES
from .utils import friendly_error, resolve_branch


@roles_required(*KITCHEN_STAFF_ROLES)
def wastage_list(request):
    branch = resolve_branch(request)
    if request.method == "POST":
        if branch is None:
            messages.error(request, "This café has no branches configured yet.")
            return redirect("web:wastage_list")
        ingredient = get_object_or_404(Ingredient, pk=request.POST.get("ingredient"), tenant=branch.tenant)
        record = WastageRecord(
            ingredient=ingredient,
            tenant=branch.tenant,
            branch=branch,
            reason=request.POST.get("reason", WastageRecord.Reason.OTHER),
            notes=request.POST.get("notes", ""),
            recorded_by=request.user,
        )
        try:
            record.quantity = request.POST.get("quantity")
            record.full_clean()
            record.save()
        except DjangoValidationError as exc:
            messages.error(request, friendly_error(exc))
        else:
            messages.success(request, f"Recorded wastage of {record}.")
        return redirect("web:wastage_list")

    records = WastageRecord.objects.select_related("ingredient", "recorded_by", "approved_by") if branch else []
    ingredient_list = Ingredient.objects.order_by("name")
    return render(
        request,
        "web/wastage_list.html",
        {
            "branch": branch,
            "records": records,
            "ingredients": ingredient_list,
            "reasons": WastageRecord.Reason.choices,
            "can_approve": request.user.is_superuser or request.user.role in MANAGER_ROLES,
        },
    )


@roles_required(*MANAGER_ROLES)
@require_POST
def wastage_approve(request, record_id):
    branch = resolve_branch(request)
    record = get_object_or_404(WastageRecord, pk=record_id, branch=branch)
    try:
        record.approve(request.user)
    except DjangoValidationError as exc:
        messages.error(request, friendly_error(exc))
    else:
        messages.success(request, "Wastage record approved.")
    return redirect("web:wastage_list")


@roles_required(*MANAGER_ROLES)
@require_POST
def wastage_reject(request, record_id):
    branch = resolve_branch(request)
    record = get_object_or_404(WastageRecord, pk=record_id, branch=branch)
    try:
        record.reject(request.user)
    except DjangoValidationError as exc:
        messages.error(request, friendly_error(exc))
    else:
        messages.success(request, "Wastage record rejected; stock restored.")
    return redirect("web:wastage_list")
