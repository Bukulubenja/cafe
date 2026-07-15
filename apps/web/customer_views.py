from django.contrib import messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.customers.models import Customer
from apps.customers.services import redeem_points
from apps.menu.models import MenuItem

from .decorators import roles_required
from .roles import FRONT_OF_HOUSE_ROLES
from .utils import friendly_error, resolve_branch


@roles_required(*FRONT_OF_HOUSE_ROLES)
def customer_list(request):
    branch = resolve_branch(request)
    if request.method == "POST":
        if branch is None:
            messages.error(request, "This café has no branches configured yet.")
            return redirect("web:customer_list")
        customer = Customer(
            tenant=branch.tenant,
            name=request.POST.get("name", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            email=request.POST.get("email", ""),
            birthday=request.POST.get("birthday") or None,
        )
        try:
            customer.full_clean()
            customer.save()
        except DjangoValidationError as exc:
            messages.error(request, friendly_error(exc))
        else:
            messages.success(request, f"Added customer {customer.name}.")
        return redirect("web:customer_list")

    query = request.GET.get("q", "").strip()
    customers = Customer.objects.select_related("favorite_item") if branch else Customer.objects.none()
    if query:
        customers = customers.filter(Q(name__icontains=query) | Q(phone__icontains=query))
    return render(
        request, "web/customer_list.html", {"branch": branch, "customers": customers, "query": query}
    )


@roles_required(*FRONT_OF_HOUSE_ROLES)
def customer_detail(request, customer_id):
    branch = resolve_branch(request)
    customer = get_object_or_404(Customer, pk=customer_id, tenant=branch.tenant if branch else None)
    transactions = customer.loyalty_transactions.select_related("menu_item", "created_by")
    redeemable_items = MenuItem.objects.filter(points_cost__isnull=False).order_by("points_cost")
    return render(
        request,
        "web/customer_detail.html",
        {
            "branch": branch,
            "customer": customer,
            "transactions": transactions,
            "redeemable_items": redeemable_items,
        },
    )


@roles_required(*FRONT_OF_HOUSE_ROLES)
@require_POST
def customer_redeem(request, customer_id):
    branch = resolve_branch(request)
    customer = get_object_or_404(Customer, pk=customer_id, tenant=branch.tenant if branch else None)
    menu_item = get_object_or_404(MenuItem, pk=request.POST.get("menu_item"), tenant=branch.tenant)
    try:
        redeem_points(customer, menu_item, branch, actor=request.user)
    except DjangoValidationError as exc:
        messages.error(request, friendly_error(exc))
    else:
        messages.success(request, f"Redeemed {menu_item.name} for {customer.name}.")
    return redirect("web:customer_detail", customer_id=customer.id)
