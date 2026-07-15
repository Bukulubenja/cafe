from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.pos.models import Order, Refund

from .decorators import roles_required
from .roles import MANAGER_ROLES, PAYMENT_ROLES
from .utils import friendly_error, resolve_branch


@roles_required(*PAYMENT_ROLES)
def refund_list(request):
    branch = resolve_branch(request)
    refunds = (
        Refund.objects.select_related("order", "requested_by", "approved_by") if branch else Refund.objects.none()
    )
    return render(
        request,
        "web/refund_list.html",
        {
            "branch": branch,
            "refunds": refunds,
            "can_approve": request.user.is_superuser or request.user.role in MANAGER_ROLES,
        },
    )


@roles_required(*PAYMENT_ROLES)
@require_POST
def refund_request(request, order_id):
    branch = resolve_branch(request)
    order = get_object_or_404(Order, pk=order_id, branch=branch)
    try:
        amount = Decimal(request.POST.get("amount", "0"))
        refund = Refund(
            order=order,
            amount=amount,
            reason=request.POST.get("reason", Refund.Reason.OTHER),
            notes=request.POST.get("notes", ""),
            requested_by=request.user,
            tenant=order.tenant,
            branch=order.branch,
        )
        refund.full_clean()
        refund.save()
    except (DjangoValidationError, InvalidOperation) as exc:
        messages.error(request, friendly_error(exc) if isinstance(exc, DjangoValidationError) else "Invalid amount.")
    else:
        messages.success(request, f"Refund of {refund.amount} UGX requested; awaiting manager approval.")
    return redirect("web:order_detail", order_id=order.id)


@roles_required(*MANAGER_ROLES)
@require_POST
def refund_approve(request, refund_id):
    branch = resolve_branch(request)
    refund = get_object_or_404(Refund, pk=refund_id, branch=branch)
    try:
        refund.approve(request.user)
    except DjangoValidationError as exc:
        messages.error(request, friendly_error(exc))
    else:
        messages.success(request, "Refund approved.")
    return redirect("web:refund_list")


@roles_required(*MANAGER_ROLES)
@require_POST
def refund_reject(request, refund_id):
    branch = resolve_branch(request)
    refund = get_object_or_404(Refund, pk=refund_id, branch=branch)
    try:
        refund.reject(request.user)
    except DjangoValidationError as exc:
        messages.error(request, friendly_error(exc))
    else:
        messages.success(request, "Refund rejected.")
    return redirect("web:refund_list")
