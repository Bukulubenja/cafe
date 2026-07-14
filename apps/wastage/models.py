from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from apps.core.models import AuditLog, BranchModel
from apps.inventory.models import Ingredient

from .services import apply_wastage, reverse_wastage


class WastageRecord(BranchModel):
    """A reported stock loss (readme: 'Chicken burnt, 3 pieces'). Deducts
    stock immediately on recording -- the ingredient is physically gone
    regardless of paperwork -- with Manager approval as an accountability
    check afterward; a rejected record restores the stock.
    """

    class Reason(models.TextChoices):
        EXPIRED = "expired", "Expired"
        BURNT = "burnt", "Burnt"
        SPOILT = "spoilt", "Spoilt"
        DROPPED = "dropped", "Dropped"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name="wastage_records")
    quantity = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(0)])
    reason = models.CharField(max_length=20, choices=Reason.choices)
    notes = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="wastage_recorded"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    approved_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="wastage_approved"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.quantity}{self.ingredient.unit} {self.ingredient.name} ({self.get_reason_display()})"

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if is_new:
                apply_wastage(self)

    def approve(self, actor):
        if self.status != self.Status.PENDING:
            raise ValidationError("Only a pending wastage record can be approved.")
        self.status = self.Status.APPROVED
        self.approved_by = actor
        self.approved_at = timezone.now()
        self.save(update_fields=["status", "approved_by", "approved_at"])
        AuditLog.objects.create(
            tenant=self.tenant, branch=self.branch, actor=actor, action="wastage.approved", object_repr=str(self)
        )

    def reject(self, actor):
        if self.status != self.Status.PENDING:
            raise ValidationError("Only a pending wastage record can be rejected.")
        with transaction.atomic():
            reverse_wastage(self)
            self.status = self.Status.REJECTED
            self.approved_by = actor
            self.approved_at = timezone.now()
            self.save(update_fields=["status", "approved_by", "approved_at"])
        AuditLog.objects.create(
            tenant=self.tenant, branch=self.branch, actor=actor, action="wastage.rejected", object_repr=str(self)
        )
