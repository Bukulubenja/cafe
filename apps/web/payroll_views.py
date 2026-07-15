from django.contrib import messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.models import User
from apps.payroll.models import PayrollRun, SalaryRecord

from .decorators import roles_required
from .roles import MANAGER_ROLES
from .utils import friendly_error, resolve_branch


@roles_required(*MANAGER_ROLES)
def salary_records(request):
    branch = resolve_branch(request)
    if request.method == "POST":
        if branch is None:
            messages.error(request, "This café has no branches configured yet.")
            return redirect("web:salary_records")
        staff = get_object_or_404(User, pk=request.POST.get("staff"), cafe=branch.tenant)
        record = SalaryRecord(
            staff=staff,
            tenant=branch.tenant,
            branch=branch,
            effective_date=request.POST.get("effective_date") or timezone.localdate(),
            notes=request.POST.get("notes", ""),
            created_by=request.user,
        )
        try:
            record.base_salary = request.POST.get("base_salary") or 0
            record.full_clean()
            record.save()
        except DjangoValidationError as exc:
            messages.error(request, friendly_error(exc))
        else:
            messages.success(request, f"Set {staff.email}'s salary to {record.base_salary} UGX from {record.effective_date}.")
        return redirect("web:salary_records")

    staff_members = User.objects.filter(cafe=branch.tenant).order_by("email") if branch else []
    current_salaries = [(staff, SalaryRecord.current_for(staff)) for staff in staff_members]
    records = SalaryRecord.objects.select_related("staff") if branch else SalaryRecord.objects.none()
    return render(
        request,
        "web/salary_records.html",
        {
            "branch": branch,
            "current_salaries": current_salaries,
            "records": records,
            "staff_members": staff_members,
        },
    )


@roles_required(*MANAGER_ROLES)
def payroll_runs(request):
    branch = resolve_branch(request)
    if request.method == "POST":
        if branch is None:
            messages.error(request, "This café has no branches configured yet.")
            return redirect("web:payroll_runs")
        try:
            run = PayrollRun.process(
                branch,
                period_start=request.POST.get("period_start"),
                period_end=request.POST.get("period_end"),
                actor=request.user,
            )
        except DjangoValidationError as exc:
            messages.error(request, friendly_error(exc))
        else:
            messages.success(request, f"Processed payroll: {run.total_paid} UGX across {run.lines.count()} staff.")
            return redirect("web:payroll_run_detail", run_id=run.id)
        return redirect("web:payroll_runs")

    runs = PayrollRun.objects.select_related("processed_by") if branch else PayrollRun.objects.none()
    return render(request, "web/payroll_runs.html", {"branch": branch, "runs": runs})


@roles_required(*MANAGER_ROLES)
def payroll_run_detail(request, run_id):
    branch = resolve_branch(request)
    run = get_object_or_404(
        PayrollRun.objects.select_related("processed_by").prefetch_related("lines__staff"), pk=run_id, branch=branch
    )
    return render(request, "web/payroll_run_detail.html", {"run": run})
