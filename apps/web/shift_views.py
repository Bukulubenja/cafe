from django.contrib import messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.shifts.models import Shift

from .decorators import roles_required
from .roles import ALL_STAFF_ROLES, MANAGER_ROLES
from .utils import friendly_error, resolve_branch


@roles_required(*ALL_STAFF_ROLES)
def my_shift(request):
    branch = resolve_branch(request)
    current = Shift.current_for(request.user)
    recent = Shift.objects.filter(staff=request.user)[:10] if branch else Shift.objects.none()
    return render(
        request, "web/my_shift.html", {"branch": branch, "current": current, "recent": recent}
    )


@roles_required(*ALL_STAFF_ROLES)
@require_POST
def shift_clock_in(request):
    branch = resolve_branch(request)
    if branch is None:
        messages.error(request, "This café has no branches configured yet.")
        return redirect("web:my_shift")
    try:
        Shift.open_for(request.user, branch)
    except DjangoValidationError as exc:
        messages.error(request, friendly_error(exc))
    else:
        messages.success(request, "Clocked in.")
    return redirect("web:my_shift")


@roles_required(*ALL_STAFF_ROLES)
@require_POST
def shift_clock_out(request, shift_id):
    shift = get_object_or_404(Shift, pk=shift_id, staff=request.user)
    try:
        shift.close(request.user)
    except DjangoValidationError as exc:
        messages.error(request, friendly_error(exc))
    else:
        messages.success(request, "Clocked out.")
    return redirect("web:my_shift")


@roles_required(*MANAGER_ROLES)
def shift_list(request):
    branch = resolve_branch(request)
    shifts = Shift.objects.select_related("staff", "closed_by") if branch else Shift.objects.none()
    return render(request, "web/shift_list.html", {"branch": branch, "shifts": shifts})


@roles_required(*MANAGER_ROLES)
@require_POST
def shift_force_close(request, shift_id):
    branch = resolve_branch(request)
    shift = get_object_or_404(Shift, pk=shift_id, branch=branch)
    try:
        shift.close(request.user)
    except DjangoValidationError as exc:
        messages.error(request, friendly_error(exc))
    else:
        messages.success(request, f"Closed {shift.staff.email}'s shift.")
    return redirect("web:shift_list")
