from django.contrib import messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.complimentary.models import ComplimentaryMeal
from apps.menu.models import MenuItem

from .decorators import roles_required
from .roles import ALL_STAFF_ROLES, MANAGER_ROLES
from .utils import friendly_error, resolve_branch


@roles_required(*ALL_STAFF_ROLES)
def complimentary_list(request):
    branch = resolve_branch(request)
    if request.method == "POST":
        if branch is None:
            messages.error(request, "This café has no branches configured yet.")
            return redirect("web:complimentary_list")
        menu_item = get_object_or_404(MenuItem, pk=request.POST.get("menu_item"), tenant=branch.tenant)
        staff_id = request.POST.get("staff")
        staff = get_object_or_404(User, pk=staff_id, cafe=branch.tenant) if staff_id else None
        meal = ComplimentaryMeal(
            staff=staff,
            department=request.POST.get("department", ""),
            menu_item=menu_item,
            tenant=branch.tenant,
            branch=branch,
            reason=request.POST.get("reason", ComplimentaryMeal.Reason.OTHER),
            notes=request.POST.get("notes", ""),
            requested_by=request.user,
        )
        try:
            meal.quantity = request.POST.get("quantity") or 1
            meal.full_clean()
            meal.save()
        except DjangoValidationError as exc:
            messages.error(request, friendly_error(exc))
        else:
            messages.success(request, f"Logged complimentary meal: {meal}.")
        return redirect("web:complimentary_list")

    meals = (
        ComplimentaryMeal.objects.select_related("staff", "menu_item", "requested_by", "approved_by")
        if branch
        else []
    )
    return render(
        request,
        "web/complimentary_list.html",
        {
            "branch": branch,
            "meals": meals,
            "menu_items": MenuItem.objects.order_by("name") if branch else [],
            "staff_members": User.objects.filter(cafe=branch.tenant).order_by("email") if branch else [],
            "reasons": ComplimentaryMeal.Reason.choices,
            "can_approve": request.user.is_superuser or request.user.role in MANAGER_ROLES,
        },
    )


@roles_required(*MANAGER_ROLES)
@require_POST
def complimentary_approve(request, meal_id):
    branch = resolve_branch(request)
    meal = get_object_or_404(ComplimentaryMeal, pk=meal_id, branch=branch)
    try:
        meal.approve(request.user)
    except DjangoValidationError as exc:
        messages.error(request, friendly_error(exc))
    else:
        messages.success(request, "Complimentary meal approved.")
    return redirect("web:complimentary_list")


@roles_required(*MANAGER_ROLES)
@require_POST
def complimentary_reject(request, meal_id):
    branch = resolve_branch(request)
    meal = get_object_or_404(ComplimentaryMeal, pk=meal_id, branch=branch)
    try:
        meal.reject(request.user)
    except DjangoValidationError as exc:
        messages.error(request, friendly_error(exc))
    else:
        messages.success(request, "Complimentary meal rejected.")
    return redirect("web:complimentary_list")
