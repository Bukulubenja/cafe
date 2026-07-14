from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import AuditLog, BranchModel


class SalaryRecord(BranchModel):
    """A staff member's salary rate, effective from a given date. Kept as
    history (not overwritten) so past payroll runs stay explainable even
    after a raise -- deliberately minimal per the readme marking Payroll
    optional: no tax/deduction modeling, just a base salary figure.
    """

    staff = models.ForeignKey(User, on_delete=models.CASCADE, related_name="salary_records")
    base_salary = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    effective_date = models.DateField(default=timezone.localdate)
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_date"]

    def __str__(self):
        return f"{self.staff}: {self.base_salary} (from {self.effective_date})"

    @classmethod
    def current_for(cls, staff, as_of=None):
        as_of = as_of or timezone.localdate()
        return cls.unscoped.filter(staff=staff, effective_date__lte=as_of).order_by("-effective_date").first()


class PayrollRun(BranchModel):
    """A processed payroll period for one branch. Immutable once created
    (no update/delete), matching DailyClosing's approach to financial
    record-keeping -- amounts are snapshotted from each staff member's
    current SalaryRecord at processing time.
    """

    period_start = models.DateField()
    period_end = models.DateField()
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    total_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period_start"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "period_start", "period_end"], name="unique_payroll_run_per_branch_period"
            ),
        ]

    def __str__(self):
        return f"Payroll {self.branch}: {self.period_start} - {self.period_end}"

    @classmethod
    def process(cls, branch, period_start, period_end, actor=None):
        if period_start > period_end:
            raise ValidationError("period_start must not be after period_end.")
        if cls.unscoped.filter(branch=branch, period_start=period_start, period_end=period_end).exists():
            raise ValidationError("A payroll run already exists for this branch and period.")

        staff_members = User.objects.filter(cafe=branch.tenant, branch=branch)
        line_data = []
        total = Decimal("0.00")
        for staff in staff_members:
            salary_record = SalaryRecord.current_for(staff, as_of=period_end)
            if salary_record is None:
                continue
            line_data.append((staff, salary_record.base_salary))
            total += salary_record.base_salary

        run = cls.objects.create(
            tenant=branch.tenant,
            branch=branch,
            period_start=period_start,
            period_end=period_end,
            processed_by=actor,
            total_paid=total,
        )
        for staff, amount in line_data:
            PayrollLine.objects.create(
                tenant=branch.tenant, branch=branch, payroll_run=run, staff=staff, amount=amount
            )

        AuditLog.objects.create(
            tenant=branch.tenant, branch=branch, actor=actor, action="payroll.processed", object_repr=str(run)
        )
        return run


class PayrollLine(BranchModel):
    """One staff member's snapshotted pay within a PayrollRun."""

    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="lines")
    staff = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="payroll_lines")
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.staff}: {self.amount}"
