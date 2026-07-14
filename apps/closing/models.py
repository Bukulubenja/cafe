from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import AuditLog, BranchModel
from apps.notifications.services import send_daily_summary
from apps.pos.models import Order


class DailyClosing(BranchModel):
    """End-of-day cash reconciliation (readme: manager clicks Close Day,
    counts cash, system shows expected cash, difference is explained and
    signed off). `cash_expected` is computed and snapshotted at close time
    from that day's paid cash orders, so it stays accurate to what closing
    actually saw even if orders are touched later.
    """

    date = models.DateField(default=timezone.localdate)
    cash_counted = models.DecimalField(max_digits=12, decimal_places=2)
    cash_expected = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255, blank=True, help_text="Explanation for any cash difference")
    closed_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)
    closed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "date"], name="unique_daily_closing_per_branch_date"),
        ]

    def __str__(self):
        return f"{self.branch} closing for {self.date}"

    @property
    def difference(self):
        return self.cash_counted - self.cash_expected

    @classmethod
    def close_day(cls, branch, cash_counted, actor=None, reason="", date=None):
        date = date or timezone.localdate()
        if cls.unscoped.filter(branch=branch, date=date).exists():
            raise ValidationError(f"{branch} has already been closed for {date}.")

        cash_orders = Order.unscoped.filter(
            branch=branch,
            status=Order.Status.PAID,
            payment_method=Order.PaymentMethod.CASH,
            closed_at__date=date,
        )
        cash_expected = sum((order.total for order in cash_orders), Decimal("0.00"))

        closing = cls.objects.create(
            tenant=branch.tenant,
            branch=branch,
            date=date,
            cash_counted=cash_counted,
            cash_expected=cash_expected,
            reason=reason,
            closed_by=actor,
        )
        AuditLog.objects.create(
            tenant=branch.tenant,
            branch=branch,
            actor=actor,
            action="daily_closing.closed",
            object_repr=f"{closing} (diff: {closing.difference})",
        )
        send_daily_summary(closing)
        return closing
