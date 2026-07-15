from django.contrib import messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.menu.menu_templates import MENU_TEMPLATES, apply_menu_template
from apps.menu.models import Category, MenuItem

from .decorators import roles_required
from .roles import MANAGER_ROLES
from .utils import friendly_error, resolve_branch


@roles_required(*MANAGER_ROLES)
def category_list(request):
    branch = resolve_branch(request)
    if request.method == "POST":
        if branch is None:
            messages.error(request, "This café has no branches configured yet.")
            return redirect("web:category_list")
        category = Category(
            tenant=branch.tenant,
            name=request.POST.get("name", "").strip(),
            sort_order=request.POST.get("sort_order") or 0,
        )
        try:
            category.full_clean()
            category.save()
        except DjangoValidationError as exc:
            messages.error(request, friendly_error(exc))
        else:
            messages.success(request, f"Added category {category.name}.")
        return redirect("web:category_list")

    categories = Category.objects.all() if branch else Category.objects.none()
    return render(request, "web/category_list.html", {"branch": branch, "categories": categories})


@roles_required(*MANAGER_ROLES)
@require_POST
def category_toggle(request, category_id):
    branch = resolve_branch(request)
    category = get_object_or_404(Category, pk=category_id, tenant=branch.tenant if branch else None)
    category.is_active = not category.is_active
    category.save(update_fields=["is_active"])
    messages.success(request, f"{category.name} is now {'active' if category.is_active else 'inactive'}.")
    return redirect("web:category_list")


@roles_required(*MANAGER_ROLES)
def menu_item_list(request):
    branch = resolve_branch(request)
    if request.method == "POST":
        if branch is None:
            messages.error(request, "This café has no branches configured yet.")
            return redirect("web:menu_item_list")
        category = get_object_or_404(Category, pk=request.POST.get("category"), tenant=branch.tenant)
        item = MenuItem(
            tenant=branch.tenant,
            category=category,
            name=request.POST.get("name", "").strip(),
            description=request.POST.get("description", ""),
            requires_kitchen=bool(request.POST.get("requires_kitchen")),
        )
        try:
            item.selling_price = request.POST.get("selling_price") or 0
            item.cost_price = request.POST.get("cost_price") or 0
            item.prep_time_minutes = request.POST.get("prep_time_minutes") or 0
            item.full_clean()
            item.save()
        except DjangoValidationError as exc:
            messages.error(request, friendly_error(exc))
        else:
            messages.success(request, f"Added menu item {item.name}.")
        return redirect("web:menu_item_list")

    items = MenuItem.objects.select_related("category") if branch else MenuItem.objects.none()
    categories = Category.objects.filter(is_active=True) if branch else []
    return render(
        request, "web/menu_item_list.html", {"branch": branch, "items": items, "categories": categories}
    )


@roles_required(*MANAGER_ROLES)
def menu_item_edit(request, item_id):
    branch = resolve_branch(request)
    item = get_object_or_404(MenuItem, pk=item_id, tenant=branch.tenant if branch else None)
    if request.method == "POST":
        item.category = get_object_or_404(Category, pk=request.POST.get("category"), tenant=branch.tenant)
        item.name = request.POST.get("name", "").strip()
        item.description = request.POST.get("description", "")
        item.requires_kitchen = bool(request.POST.get("requires_kitchen"))
        item.is_available = bool(request.POST.get("is_available"))
        try:
            item.selling_price = request.POST.get("selling_price") or 0
            item.cost_price = request.POST.get("cost_price") or 0
            item.vat_rate = request.POST.get("vat_rate") or 0
            item.prep_time_minutes = request.POST.get("prep_time_minutes") or 0
            item.points_cost = request.POST.get("points_cost") or None
            item.full_clean()
            item.save()
        except DjangoValidationError as exc:
            messages.error(request, friendly_error(exc))
        else:
            messages.success(request, f"Updated {item.name}.")
            return redirect("web:menu_item_list")

    categories = Category.objects.all()
    return render(request, "web/menu_item_edit.html", {"branch": branch, "item": item, "categories": categories})


@roles_required(*MANAGER_ROLES)
def menu_templates(request):
    branch = resolve_branch(request)
    templates = [{"key": key, **data} for key, data in MENU_TEMPLATES.items()]
    return render(request, "web/menu_templates.html", {"branch": branch, "templates": templates})


@roles_required(*MANAGER_ROLES)
@require_POST
def menu_template_apply(request, template_key):
    branch = resolve_branch(request)
    if branch is None:
        messages.error(request, "This café has no branches configured yet.")
        return redirect("web:menu_templates")
    if template_key not in MENU_TEMPLATES:
        messages.error(request, "Unknown menu template.")
        return redirect("web:menu_templates")

    created = apply_menu_template(template_key, branch.tenant, branch=branch)
    label = MENU_TEMPLATES[template_key]["label"]
    messages.success(
        request,
        f"Applied {label}: added {created['categories']} categor{'y' if created['categories'] == 1 else 'ies'}, "
        f"{created['menu_items']} menu item(s), {created['ingredients']} new ingredient(s), "
        f"{created['stock_items']} stock item(s).",
    )
    return redirect("web:menu_item_list")
