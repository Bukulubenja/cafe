from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.inventory.models import Ingredient
from apps.notifications.services import send_purchase_order
from apps.purchasing.models import PurchaseOrder, PurchaseOrderLine, Supplier, SupplierLedgerEntry

from .decorators import roles_required
from .roles import MANAGER_ROLES
from .utils import csv_response, friendly_error, resolve_branch


@roles_required(*MANAGER_ROLES)
def suppliers(request):
    branch = resolve_branch(request)
    if request.method == "POST":
        if branch is None:
            messages.error(request, "This café has no branches configured yet.")
            return redirect("web:suppliers")
        supplier = Supplier(
            tenant=branch.tenant,
            name=request.POST.get("name", "").strip(),
            phone=request.POST.get("phone", ""),
            email=request.POST.get("email", ""),
            address=request.POST.get("address", ""),
        )
        try:
            supplier.full_clean()
            supplier.save()
        except DjangoValidationError as exc:
            messages.error(request, friendly_error(exc))
        else:
            messages.success(request, f"Added supplier {supplier.name}.")
        return redirect("web:suppliers")

    supplier_list = Supplier.objects.order_by("name") if branch else []
    return render(request, "web/suppliers.html", {"branch": branch, "suppliers": supplier_list})


@roles_required(*MANAGER_ROLES)
def supplier_ledger_download(request):
    branch = resolve_branch(request)
    if branch is None:
        messages.error(request, "This café has no branches configured yet.")
        return redirect("web:suppliers")

    entries = SupplierLedgerEntry.objects.select_related("supplier", "purchase_order", "created_by")
    rows = (
        (
            e.created_at,
            e.supplier.name,
            e.get_entry_type_display(),
            e.amount,
            e.purchase_order_id or "",
            e.created_by.email if e.created_by else "",
            e.notes,
        )
        for e in entries
    )
    return csv_response(
        f"supplier-ledger_{branch.tenant.name}.csv",
        ("Date", "Supplier", "Type", "Amount", "Purchase order", "Recorded by", "Notes"),
        rows,
    )


@roles_required(*MANAGER_ROLES)
@require_POST
def supplier_pay(request, supplier_id):
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    try:
        amount = Decimal(request.POST.get("amount", "0"))
        supplier.pay(amount, actor=request.user, notes=request.POST.get("notes", ""))
    except (DjangoValidationError, InvalidOperation) as exc:
        messages.error(request, friendly_error(exc) if isinstance(exc, DjangoValidationError) else "Invalid amount.")
    else:
        messages.success(request, f"Recorded payment to {supplier.name}.")
    return redirect("web:suppliers")


@roles_required(*MANAGER_ROLES)
def purchase_orders(request):
    branch = resolve_branch(request)
    orders = PurchaseOrder.objects.select_related("supplier").order_by("-created_at") if branch else []
    supplier_list = Supplier.objects.order_by("name") if branch else []
    return render(
        request, "web/purchase_orders.html", {"branch": branch, "orders": orders, "suppliers": supplier_list}
    )


@roles_required(*MANAGER_ROLES)
@require_POST
def purchase_order_new(request):
    branch = resolve_branch(request)
    if branch is None:
        messages.error(request, "This café has no branches configured yet.")
        return redirect("web:purchase_orders")
    supplier = get_object_or_404(Supplier, pk=request.POST.get("supplier"), tenant=branch.tenant)
    order = PurchaseOrder.objects.create(
        supplier=supplier, created_by=request.user, tenant=branch.tenant, branch=branch
    )
    return redirect("web:purchase_order_detail", order_id=order.id)


@roles_required(*MANAGER_ROLES)
def purchase_order_detail(request, order_id):
    branch = resolve_branch(request)
    order = get_object_or_404(
        PurchaseOrder.objects.select_related("supplier").prefetch_related("lines__ingredient"),
        pk=order_id,
        branch=branch,
    )
    ingredient_list = Ingredient.objects.order_by("name")
    return render(request, "web/purchase_order_detail.html", {"order": order, "ingredients": ingredient_list})


@roles_required(*MANAGER_ROLES)
@require_POST
def purchase_order_add_line(request, order_id):
    branch = resolve_branch(request)
    order = get_object_or_404(PurchaseOrder, pk=order_id, branch=branch)
    if order.status != PurchaseOrder.Status.PENDING:
        messages.error(request, "Cannot add lines to a purchase order that is not pending.")
        return redirect("web:purchase_order_detail", order_id=order.id)

    ingredient = get_object_or_404(Ingredient, pk=request.POST.get("ingredient"), tenant=branch.tenant)
    line = PurchaseOrderLine(purchase_order=order, ingredient=ingredient, tenant=branch.tenant, branch=branch)
    try:
        line.quantity = request.POST.get("quantity")
        line.unit_cost = request.POST.get("unit_cost")
        line.full_clean()
        line.save()
    except DjangoValidationError as exc:
        messages.error(request, friendly_error(exc))
    else:
        messages.success(request, f"Added {line.quantity}{ingredient.unit} {ingredient.name}.")
    return redirect("web:purchase_order_detail", order_id=order.id)


@roles_required(*MANAGER_ROLES)
@require_POST
def purchase_order_receive(request, order_id):
    branch = resolve_branch(request)
    order = get_object_or_404(PurchaseOrder, pk=order_id, branch=branch)
    try:
        order.receive(actor=request.user)
    except DjangoValidationError as exc:
        messages.error(request, friendly_error(exc))
    else:
        messages.success(request, "Purchase order received; stock updated.")
    return redirect("web:purchase_order_detail", order_id=order.id)


@roles_required(*MANAGER_ROLES)
@require_POST
def purchase_order_cancel(request, order_id):
    branch = resolve_branch(request)
    order = get_object_or_404(PurchaseOrder, pk=order_id, branch=branch)
    try:
        order.cancel(actor=request.user)
    except DjangoValidationError as exc:
        messages.error(request, friendly_error(exc))
    else:
        messages.success(request, "Purchase order cancelled.")
    return redirect("web:purchase_order_detail", order_id=order.id)


@roles_required(*MANAGER_ROLES)
@require_POST
def purchase_order_notify_supplier(request, order_id):
    branch = resolve_branch(request)
    order = get_object_or_404(PurchaseOrder, pk=order_id, branch=branch)
    if not order.lines.exists():
        messages.error(request, "Add at least one line before notifying the supplier.")
    else:
        send_purchase_order(order)
        messages.success(request, "Supplier notified.")
    return redirect("web:purchase_order_detail", order_id=order.id)
