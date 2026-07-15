from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.contrib.auth.views import LogoutView as DjangoLogoutView
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.menu.models import Category, MenuItem
from apps.pos.models import Order, OrderItem, Table
from apps.reports.services import build_dashboard_data

from .decorators import roles_required
from .utils import friendly_error, resolve_branch

MANAGER_ROLES = (User.Role.OWNER, User.Role.MANAGER)
FRONT_OF_HOUSE_ROLES = (User.Role.OWNER, User.Role.MANAGER, User.Role.WAITER, User.Role.CASHIER)
ORDER_WRITE_ROLES = (User.Role.OWNER, User.Role.MANAGER, User.Role.WAITER)
PAYMENT_ROLES = (User.Role.OWNER, User.Role.MANAGER, User.Role.WAITER, User.Role.CASHIER)
KITCHEN_VIEW_ROLES = (User.Role.OWNER, User.Role.MANAGER, User.Role.CHEF, User.Role.WAITER, User.Role.CASHIER)


class LoginView(DjangoLoginView):
    template_name = "web/login.html"

    def get_success_url(self):
        return reverse("web:home")


class LogoutView(DjangoLogoutView):
    next_page = "web:login"


# Django's LogoutView already only responds to POST (view-level +
# require_POST just documents/enforces the intent explicitly here).
logout_view = require_POST(LogoutView.as_view())


@login_required(login_url="web:login")
def home(request):
    user = request.user
    if user.is_superuser or user.role in MANAGER_ROLES:
        return redirect("web:dashboard")
    if user.role == User.Role.CHEF:
        return redirect("web:kitchen")
    return redirect("web:tables")


@roles_required(*MANAGER_ROLES)
def dashboard(request):
    branch = resolve_branch(request)
    data = build_dashboard_data() if branch else None
    return render(request, "web/dashboard.html", {"branch": branch, "data": data})


@roles_required(*FRONT_OF_HOUSE_ROLES)
def tables(request):
    branch = resolve_branch(request)
    table_list = Table.objects.filter(branch=branch).order_by("name") if branch else []
    return render(request, "web/tables.html", {"branch": branch, "tables": table_list})


@roles_required(*ORDER_WRITE_ROLES)
def order_for_table(request, table_id):
    branch = resolve_branch(request)
    table = get_object_or_404(Table, pk=table_id, branch=branch)
    order = Order.objects.filter(table=table, status=Order.Status.OPEN).first()
    if order is None:
        order = Order.objects.create(
            table=table,
            order_type=Order.OrderType.DINE_IN,
            created_by=request.user,
            tenant=branch.tenant,
            branch=branch,
        )
        table.status = Table.Status.OCCUPIED
        table.save(update_fields=["status"])
    return redirect("web:order_detail", order_id=order.id)


@roles_required(*ORDER_WRITE_ROLES)
@require_POST
def new_takeaway_order(request):
    branch = resolve_branch(request)
    if branch is None:
        messages.error(request, "This café has no branches configured yet.")
        return redirect("web:tables")
    order = Order.objects.create(
        order_type=Order.OrderType.TAKEAWAY,
        created_by=request.user,
        tenant=branch.tenant,
        branch=branch,
    )
    return redirect("web:order_detail", order_id=order.id)


@roles_required(*FRONT_OF_HOUSE_ROLES)
def order_detail(request, order_id):
    branch = resolve_branch(request)
    order = get_object_or_404(
        Order.objects.select_related("table").prefetch_related("items__menu_item"), pk=order_id, branch=branch
    )
    category_list = list(
        Category.objects.filter(is_active=True).order_by("sort_order", "name").prefetch_related("items")
    )
    for category in category_list:
        for item in category.items.all():
            item.available_now = item.is_available_at(branch)

    return render(
        request,
        "web/order.html",
        {
            "order": order,
            "categories": category_list,
            "payment_methods": Order.PaymentMethod.choices,
            "can_edit": request.user.is_superuser or request.user.role in ORDER_WRITE_ROLES,
            "can_pay": request.user.is_superuser or request.user.role in PAYMENT_ROLES,
        },
    )


@roles_required(*ORDER_WRITE_ROLES)
@require_POST
def order_add_item(request, order_id):
    branch = resolve_branch(request)
    order = get_object_or_404(Order, pk=order_id, branch=branch)

    if order.status != Order.Status.OPEN:
        messages.error(request, "Cannot add items to an order that is not open.")
        return redirect("web:order_detail", order_id=order.id)

    menu_item = get_object_or_404(MenuItem, pk=request.POST.get("menu_item"), tenant=branch.tenant)
    if not menu_item.is_available_at(branch):
        messages.error(request, f"{menu_item.name} is currently unavailable at this branch (out of stock).")
        return redirect("web:order_detail", order_id=order.id)

    try:
        quantity = max(1, int(request.POST.get("quantity", 1)))
    except (TypeError, ValueError):
        quantity = 1

    try:
        OrderItem.objects.create(
            order=order,
            menu_item=menu_item,
            quantity=quantity,
            notes=request.POST.get("notes", ""),
            tenant=branch.tenant,
            branch=branch,
        )
    except DjangoValidationError as exc:
        messages.error(request, friendly_error(exc))
    else:
        messages.success(request, f"Added {quantity} x {menu_item.name}.")
    return redirect("web:order_detail", order_id=order.id)


@roles_required(*PAYMENT_ROLES)
@require_POST
def order_pay(request, order_id):
    branch = resolve_branch(request)
    order = get_object_or_404(Order, pk=order_id, branch=branch)
    try:
        order.mark_paid(request.POST.get("payment_method"), actor=request.user)
    except DjangoValidationError as exc:
        messages.error(request, friendly_error(exc))
    else:
        messages.success(request, "Order marked as paid.")
    return redirect("web:order_detail", order_id=order.id)


@roles_required(*ORDER_WRITE_ROLES)
@require_POST
def order_cancel(request, order_id):
    branch = resolve_branch(request)
    order = get_object_or_404(Order, pk=order_id, branch=branch)
    try:
        order.cancel(actor=request.user)
    except DjangoValidationError as exc:
        messages.error(request, friendly_error(exc))
    else:
        messages.success(request, "Order cancelled.")
    return redirect("web:order_detail", order_id=order.id)


@roles_required(*KITCHEN_VIEW_ROLES)
def kitchen(request):
    branch = resolve_branch(request)
    return render(request, "web/kitchen.html", {"branch": branch})
