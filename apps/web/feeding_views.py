from django.contrib import messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.menu.models import MenuItem
from apps.staff_feeding.models import FeedingRecord, FeedingSlot

from .decorators import roles_required
from .roles import ALL_STAFF_ROLES, MANAGER_ROLES
from .utils import friendly_error, resolve_branch


@roles_required(*ALL_STAFF_ROLES)
def feeding_list(request):
    branch = resolve_branch(request)
    is_manager = request.user.is_superuser or request.user.role in MANAGER_ROLES

    if request.method == "POST":
        if branch is None:
            messages.error(request, "This café has no branches configured yet.")
            return redirect("web:feeding_list")
        record = FeedingRecord(
            staff=request.user,
            slot_id=request.POST.get("slot"),
            menu_item_id=request.POST.get("menu_item"),
            tenant=branch.tenant,
            branch=branch,
        )
        try:
            record.full_clean()
            record.save()
        except DjangoValidationError as exc:
            messages.error(request, friendly_error(exc))
        else:
            messages.success(request, f"Logged {record.slot} for {record.date}.")
        return redirect("web:feeding_list")

    records = (
        FeedingRecord.objects.select_related("staff", "slot", "menu_item") if branch else FeedingRecord.objects.none()
    )
    if not is_manager:
        records = records.filter(staff=request.user)
    slots = FeedingSlot.objects.filter(tenant=branch.tenant, is_active=True) if branch else []
    return render(
        request,
        "web/feeding_list.html",
        {
            "branch": branch,
            "records": records,
            "slots": slots,
            "menu_items": MenuItem.objects.order_by("name") if branch else [],
            "is_manager": is_manager,
        },
    )


@roles_required(*MANAGER_ROLES)
def feeding_slots(request):
    branch = resolve_branch(request)
    if request.method == "POST":
        if branch is None:
            messages.error(request, "This café has no branches configured yet.")
            return redirect("web:feeding_slots")
        slot = FeedingSlot(
            tenant=branch.tenant,
            name=request.POST.get("name", FeedingSlot.Name.OTHER),
            start_time=request.POST.get("start_time") or None,
            end_time=request.POST.get("end_time") or None,
        )
        try:
            slot.full_clean()
            slot.save()
        except DjangoValidationError as exc:
            messages.error(request, friendly_error(exc))
        else:
            messages.success(request, f"Added feeding slot {slot}.")
        return redirect("web:feeding_slots")

    slot_list = FeedingSlot.objects.filter(tenant=branch.tenant).order_by("start_time") if branch else []
    return render(
        request,
        "web/feeding_slots.html",
        {"branch": branch, "slots": slot_list, "names": FeedingSlot.Name.choices},
    )
