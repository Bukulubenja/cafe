from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import BranchModel


class Shift(BranchModel):
    """One staff member's clocked-in work session at a branch (readme:
    Manager can "Open shift"/"Close shift"; the Shift Accountability
    differentiator wants every transaction, refund, stock adjustment, and
    complimentary meal traceable to the staff member AND the shift they
    were on). Every staff role clocks their own shift in/out; a manager can
    additionally force-close someone else's shift (e.g. they forgot to
    clock out) for oversight.
    """

    staff = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="shifts")
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="shifts_closed"
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-opened_at"]

    def __str__(self):
        status = "open" if self.is_open else self.closed_at.strftime("%H:%M")
        return f"{self.staff} @ {self.branch} ({self.opened_at:%Y-%m-%d %H:%M} - {status})"

    @property
    def is_open(self):
        return self.closed_at is None

    @classmethod
    def open_for(cls, staff, branch):
        if cls.unscoped.filter(staff=staff, closed_at__isnull=True).exists():
            raise ValidationError(f"{staff} already has an open shift.")
        return cls.objects.create(staff=staff, tenant=branch.tenant, branch=branch)

    @classmethod
    def current_for(cls, staff):
        """The staff member's currently open shift, if any -- used to
        auto-link new transactions (e.g. Order) to a shift without
        requiring every screen to ask for one explicitly.
        """
        return cls.unscoped.filter(staff=staff, closed_at__isnull=True).order_by("-opened_at").first()

    def close(self, actor=None):
        if not self.is_open:
            raise ValidationError("This shift is already closed.")
        self.closed_at = timezone.now()
        self.closed_by = actor
        self.save(update_fields=["closed_at", "closed_by"])
