from django.db import models, transaction
from django.utils import timezone

from apps.core.models import BranchModel, TenantModel
from apps.inventory.services import deduct_stock_for_order_item
from apps.menu.models import MenuItem


class FeedingSlot(TenantModel):
    """A scheduled staff-feeding slot (readme: Morning Tea, Lunch, Evening
    Tea), shared across a café's branches. Distinct from ComplimentaryMeal,
    which is for ad-hoc exceptional giveaways requiring Manager approval --
    this is the routine, expected daily staff feeding schedule.
    """

    class Name(models.TextChoices):
        MORNING_TEA = "morning_tea", "Morning Tea"
        LUNCH = "lunch", "Lunch"
        EVENING_TEA = "evening_tea", "Evening Tea"
        OTHER = "other", "Other"

    name = models.CharField(max_length=20, choices=Name.choices)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["start_time", "name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_feeding_slot_name_per_cafe"),
        ]

    def __str__(self):
        return self.get_name_display()


class FeedingRecord(BranchModel):
    """One staff member eating at one scheduled slot on one day. Deducts
    stock immediately on creation -- the meal already happened at the
    scheduled time, no approval gate needed (unlike ComplimentaryMeal).
    """

    staff = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="feeding_records")
    slot = models.ForeignKey(FeedingSlot, on_delete=models.PROTECT, related_name="records")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT, related_name="feeding_records")
    date = models.DateField(default=timezone.localdate)
    # Snapshotted at creation so cost reports stay accurate if the menu's
    # cost price changes later.
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "staff", "slot", "date"], name="unique_feeding_record_per_staff_slot_day"
            ),
        ]

    def __str__(self):
        return f"{self.staff} - {self.slot} ({self.date})"

    @property
    def quantity(self):
        # deduct_stock_for_order_item expects a `quantity`; always one
        # serving per feeding record.
        return 1

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        if is_new and self.unit_cost is None:
            self.unit_cost = self.menu_item.cost_price
        with transaction.atomic():
            super().save(*args, **kwargs)
            if is_new:
                deduct_stock_for_order_item(self)
