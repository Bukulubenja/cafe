from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import AuditLog, BranchModel
from apps.inventory.services import deduct_stock_for_order_item
from apps.menu.models import MenuItem


class ComplimentaryMeal(BranchModel):
    """A free/comped meal (readme: manager lunch, waiter breakfast, chef
    tea, owner guests, VIP, customer complaint, promotion). Unlike wastage,
    stock is only deducted once a Manager approves the request -- a comp
    meal hasn't been given away yet, so approval is a real gate against the
    revenue leakage the readme calls out, not just after-the-fact bookkeeping.
    """

    class Reason(models.TextChoices):
        MANAGER_LUNCH = "manager_lunch", "Manager lunch"
        WAITER_BREAKFAST = "waiter_breakfast", "Waiter breakfast"
        CHEF_TEA = "chef_tea", "Chef tea"
        OWNER_GUEST = "owner_guest", "Owner guest"
        VIP = "vip", "VIP"
        CUSTOMER_COMPLAINT = "customer_complaint", "Customer complaint"
        PROMOTION = "promotion", "Promotion"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    staff = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="complimentary_meals_received"
    )
    department = models.CharField(max_length=100, blank=True)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT, related_name="complimentary_meals")
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    reason = models.CharField(max_length=30, choices=Reason.choices)
    notes = models.CharField(max_length=255, blank=True)
    requested_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="complimentary_meals_logged"
    )
    # Snapshotted at approval time so monthly cost reporting stays accurate
    # even if the menu item's cost price changes later.
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    approved_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="complimentary_meals_approved"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.quantity} x {self.menu_item.name} ({self.get_reason_display()})"

    @property
    def total_cost(self):
        if self.unit_cost is None:
            return None
        return self.unit_cost * self.quantity

    def approve(self, actor):
        if self.status != self.Status.PENDING:
            raise ValidationError("Only a pending complimentary meal can be approved.")
        deduct_stock_for_order_item(self)
        self.status = self.Status.APPROVED
        self.approved_by = actor
        self.approved_at = timezone.now()
        self.unit_cost = self.menu_item.cost_price
        self.save(update_fields=["status", "approved_by", "approved_at", "unit_cost"])
        AuditLog.objects.create(
            tenant=self.tenant, branch=self.branch, actor=actor, action="complimentary.approved", object_repr=str(self)
        )

    def reject(self, actor):
        if self.status != self.Status.PENDING:
            raise ValidationError("Only a pending complimentary meal can be rejected.")
        self.status = self.Status.REJECTED
        self.approved_by = actor
        self.approved_at = timezone.now()
        self.save(update_fields=["status", "approved_by", "approved_at"])
        AuditLog.objects.create(
            tenant=self.tenant, branch=self.branch, actor=actor, action="complimentary.rejected", object_repr=str(self)
        )
