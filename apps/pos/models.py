from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import AuditLog, BranchModel
from apps.menu.models import MenuItem


class Table(BranchModel):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        RESERVED = "reserved", "Reserved"
        OCCUPIED = "occupied", "Occupied"

    name = models.CharField(max_length=50)
    capacity = models.PositiveIntegerField(default=4)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_table_name_per_branch"),
        ]

    def __str__(self):
        return f"{self.name} ({self.branch})"


class Order(BranchModel):
    class OrderType(models.TextChoices):
        DINE_IN = "dine_in", "Dine-in"
        TAKEAWAY = "takeaway", "Takeaway"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        MOBILE_MONEY = "mobile_money", "Mobile Money"
        CARD = "card", "Card"

    table = models.ForeignKey(Table, on_delete=models.PROTECT, null=True, blank=True, related_name="orders")
    order_type = models.CharField(max_length=20, choices=OrderType.choices, default=OrderType.DINE_IN)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders_created"
    )
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, blank=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]

    def __str__(self):
        return f"Order #{self.pk} ({self.get_status_display()})"

    def clean(self):
        super().clean()
        if self.order_type == self.OrderType.DINE_IN and self.table_id is None:
            raise ValidationError({"table": "Dine-in orders must have a table."})

    @property
    def active_items(self):
        return self.items.exclude(kitchen_status=OrderItem.KitchenStatus.CANCELLED)

    @property
    def subtotal(self):
        total = sum((item.line_subtotal for item in self.active_items), Decimal("0.00"))
        return total

    @property
    def vat_total(self):
        total = sum((item.line_vat for item in self.active_items), Decimal("0.00"))
        return total

    @property
    def total(self):
        return self.subtotal + self.vat_total

    def mark_paid(self, payment_method, actor=None):
        if self.status != self.Status.OPEN:
            raise ValidationError("Only an open order can be marked as paid.")
        self.status = self.Status.PAID
        self.payment_method = payment_method
        self.closed_at = timezone.now()
        self.save(update_fields=["status", "payment_method", "closed_at"])
        if self.table_id:
            self.table.status = Table.Status.AVAILABLE
            self.table.save(update_fields=["status"])
        AuditLog.objects.create(
            branch=self.branch, actor=actor, action="order.paid", object_repr=str(self)
        )

    def cancel(self, actor=None):
        if self.status != self.Status.OPEN:
            raise ValidationError("Only an open order can be cancelled.")
        self.status = self.Status.CANCELLED
        self.closed_at = timezone.now()
        self.save(update_fields=["status", "closed_at"])
        if self.table_id:
            self.table.status = Table.Status.AVAILABLE
            self.table.save(update_fields=["status"])
        AuditLog.objects.create(
            branch=self.branch, actor=actor, action="order.cancelled", object_repr=str(self)
        )


class OrderItem(BranchModel):
    class KitchenStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        COOKING = "cooking", "Cooking"
        READY = "ready", "Ready"
        SERVED = "served", "Served"
        CANCELLED = "cancelled", "Cancelled"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    # Snapshotted at creation time so historical orders stay accurate even if
    # the menu item's price/VAT/kitchen requirement changes later.
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    requires_kitchen = models.BooleanField(default=True)
    kitchen_status = models.CharField(max_length=20, choices=KitchenStatus.choices, default=KitchenStatus.PENDING)
    notes = models.CharField(max_length=255, blank=True)
    started_cooking_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    served_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.quantity} x {self.menu_item.name}"

    def save(self, *args, **kwargs):
        if self._state.adding:
            # Snapshot current menu item state so historical orders stay
            # accurate even if the menu changes later.
            if not self.unit_price:
                self.unit_price = self.menu_item.selling_price
            if not self.vat_rate:
                self.vat_rate = self.menu_item.vat_rate
            self.requires_kitchen = self.menu_item.requires_kitchen
            if not self.requires_kitchen:
                self.kitchen_status = self.KitchenStatus.SERVED
                self.served_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def line_subtotal(self):
        return self.unit_price * self.quantity

    @property
    def line_vat(self):
        return (self.line_subtotal * self.vat_rate / Decimal("100")).quantize(Decimal("0.01"))

    def _transition(self, expected_current, new_status, timestamp_field):
        if self.kitchen_status != expected_current:
            raise ValidationError(
                f"Cannot move to '{new_status}' from '{self.kitchen_status}'; expected '{expected_current}'."
            )
        self.kitchen_status = new_status
        setattr(self, timestamp_field, timezone.now())
        self.save(update_fields=["kitchen_status", timestamp_field])

    def mark_cooking(self):
        self._transition(self.KitchenStatus.PENDING, self.KitchenStatus.COOKING, "started_cooking_at")

    def mark_ready(self):
        self._transition(self.KitchenStatus.COOKING, self.KitchenStatus.READY, "ready_at")

    def mark_served(self):
        self._transition(self.KitchenStatus.READY, self.KitchenStatus.SERVED, "served_at")

    def cancel(self):
        if self.kitchen_status in (self.KitchenStatus.SERVED, self.KitchenStatus.CANCELLED):
            raise ValidationError("Cannot cancel an item that has already been served or cancelled.")
        self.kitchen_status = self.KitchenStatus.CANCELLED
        self.save(update_fields=["kitchen_status"])
