from django.contrib import messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.inventory.models import Ingredient, StockItem

from .decorators import roles_required
from .utils import friendly_error, resolve_branch

MANAGER_ROLES = (User.Role.OWNER, User.Role.MANAGER)


@roles_required(*MANAGER_ROLES)
def stock_list(request):
    branch = resolve_branch(request)
    items = StockItem.objects.select_related("ingredient").order_by("ingredient__name") if branch else []
    return render(request, "web/stock_list.html", {"branch": branch, "items": items})


@roles_required(*MANAGER_ROLES)
@require_POST
def stock_adjust(request, stock_item_id):
    branch = resolve_branch(request)
    item = get_object_or_404(StockItem, pk=stock_item_id, branch=branch)
    try:
        item.quantity_on_hand = request.POST.get("quantity_on_hand")
        item.minimum_quantity = request.POST.get("minimum_quantity")
        item.full_clean()
        item.save(update_fields=["quantity_on_hand", "minimum_quantity", "updated_at"])
    except (DjangoValidationError, TypeError, ValueError) as exc:
        messages.error(request, friendly_error(exc) if isinstance(exc, DjangoValidationError) else "Invalid quantity.")
    else:
        messages.success(request, f"Updated stock for {item.ingredient.name}.")
    return redirect("web:stock_list")


@roles_required(*MANAGER_ROLES)
def stock_new(request):
    branch = resolve_branch(request)
    if request.method == "POST":
        if branch is None:
            messages.error(request, "This café has no branches configured yet.")
            return redirect("web:stock_list")
        ingredient = get_object_or_404(Ingredient, pk=request.POST.get("ingredient"), tenant=branch.tenant)
        item = StockItem(
            ingredient=ingredient,
            tenant=branch.tenant,
            branch=branch,
            supplier_name=request.POST.get("supplier_name", ""),
        )
        try:
            item.quantity_on_hand = request.POST.get("quantity_on_hand") or 0
            item.minimum_quantity = request.POST.get("minimum_quantity") or 0
            item.buying_price = request.POST.get("buying_price") or 0
            item.full_clean()
            item.save()
        except DjangoValidationError as exc:
            messages.error(request, friendly_error(exc))
            return redirect("web:stock_new")
        messages.success(request, f"Added {ingredient.name} to stock.")
        return redirect("web:stock_list")

    existing_ids = StockItem.objects.filter(branch=branch).values_list("ingredient_id", flat=True) if branch else []
    available_ingredients = Ingredient.objects.exclude(pk__in=list(existing_ids)).order_by("name") if branch else []
    return render(request, "web/stock_new.html", {"branch": branch, "ingredients": available_ingredients})


@roles_required(*MANAGER_ROLES)
def ingredients(request):
    branch = resolve_branch(request)
    if request.method == "POST":
        if branch is None:
            messages.error(request, "This café has no branches configured yet.")
            return redirect("web:ingredients")
        ingredient = Ingredient(
            tenant=branch.tenant,
            name=request.POST.get("name", "").strip(),
            category=request.POST.get("category", Ingredient.Category.KITCHEN),
            unit=request.POST.get("unit", Ingredient.Unit.PIECE),
        )
        try:
            ingredient.full_clean()
            ingredient.save()
        except DjangoValidationError as exc:
            messages.error(request, friendly_error(exc))
        else:
            messages.success(request, f"Added ingredient {ingredient.name}.")
        return redirect("web:ingredients")

    ingredient_list = Ingredient.objects.order_by("name")
    return render(
        request,
        "web/ingredients.html",
        {
            "branch": branch,
            "ingredients": ingredient_list,
            "categories": Ingredient.Category.choices,
            "units": Ingredient.Unit.choices,
        },
    )
