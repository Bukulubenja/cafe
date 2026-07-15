from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from apps.core.models import AuditLog, BranchModel
from apps.customers.services import award_points_for_order
from apps.inventory.services import deduct_stock_for_order_item
from apps.menu.models import MenuItem
from apps.notifications.services import send_receipt

from .realtime import broadcast_kitchen_update


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
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, blank=True)
    # Client-generated (offline-first): lets a POS terminal that queued this
    # order while offline retry the create after reconnecting without risk
    # of double-booking the sale if the first attempt actually landed.
    client_id = models.UUIDField(null=True, blank=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "client_id"], name="unique_order_client_id_per_cafe"),
        ]

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
        award_points_for_order(self)
        send_receipt(self)

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

    def transfer_table(self, new_table, actor=None):
        """Move a dine-in order to a different table (readme: Waiter can
        "Transfer tables") -- e.g. a party asks to move, or two small
        tables need consolidating onto a bigger one.
        """
        if self.status != self.Status.OPEN:
            raise ValidationError("Only an open order can be transferred.")
        if self.order_type != self.OrderType.DINE_IN or self.table_id is None:
            raise ValidationError("Only a dine-in order can be transferred to another table.")
        if new_table.id == self.table_id:
            raise ValidationError("Order is already at that table.")
        if new_table.branch_id != self.branch_id:
            raise ValidationError("Table does not belong to this order's branch.")
        if Order.objects.filter(table=new_table, status=self.Status.OPEN).exists():
            raise ValidationError(f"{new_table.name} already has an open order.")

        with transaction.atomic():
            old_table = self.table
            self.table = new_table
            self.save(update_fields=["table"])
            new_table.status = Table.Status.OCCUPIED
            new_table.save(update_fields=["status"])
            old_table.status = Table.Status.AVAILABLE
            old_table.save(update_fields=["status"])
        AuditLog.objects.create(
            branch=self.branch,
            actor=actor,
            action="order.table_transferred",
            object_repr=f"{self}: {old_table.name} -> {new_table.name}",
        )

    def split_off(self, item_ids, actor=None):
        """Move the given order items onto a new order for separate payment
        (readme: Waiter can "Split bills"). Whole order-item lines move
        together as a unit -- to split a single line's quantity between
        bills, add it to the order as separate lines to begin with.
        """
        if self.status != self.Status.OPEN:
            raise ValidationError("Only an open order can be split.")
        items = list(self.active_items.filter(id__in=item_ids))
        if not items:
            raise ValidationError("Select at least one item to split off.")
        if len(items) == self.active_items.count():
            raise ValidationError("Cannot split off every item; the original order would be left empty.")

        with transaction.atomic():
            new_order = Order.objects.create(
                table=self.table,
                order_type=self.order_type,
                created_by=actor,
                tenant=self.tenant,
                branch=self.branch,
            )
            for item in items:
                item.order = new_order
                item.save(update_fields=["order"])
        AuditLog.objects.create(
            branch=self.branch, actor=actor, action="order.split", object_repr=f"{self} -> {new_order}"
        )
        return new_order


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
    # Client-generated (offline-first): same idempotent-retry purpose as
    # Order.client_id, for items added to an order while offline.
    client_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "client_id"], name="unique_order_item_client_id_per_cafe"),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.menu_item.name}"

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        if is_new:
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
        with transaction.atomic():
            super().save(*args, **kwargs)
            # Non-kitchen items (e.g. bottled drinks) skip the kitchen
            # entirely and are served immediately, so their stock is
            # consumed right away. Kitchen items deduct later, when the
            # chef actually starts cooking them (see mark_cooking).
            if is_new and not self.requires_kitchen:
                deduct_stock_for_order_item(self)
        if is_new and self.requires_kitchen:
            broadcast_kitchen_update(self)

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
        if self.kitchen_status != self.KitchenStatus.PENDING:
            raise ValidationError(
                f"Cannot move to 'cooking' from '{self.kitchen_status}'; expected 'pending'."
            )
        with transaction.atomic():
            deduct_stock_for_order_item(self)
            self._transition(self.KitchenStatus.PENDING, self.KitchenStatus.COOKING, "started_cooking_at")
        # Broadcast only after the transaction commits -- a channel-layer
        # send isn't transactional, so firing it inside the atomic block
        # could notify about a change that then gets rolled back.
        broadcast_kitchen_update(self)

    def mark_ready(self):
        self._transition(self.KitchenStatus.COOKING, self.KitchenStatus.READY, "ready_at")
        broadcast_kitchen_update(self)

    def mark_served(self):
        self._transition(self.KitchenStatus.READY, self.KitchenStatus.SERVED, "served_at")
        broadcast_kitchen_update(self)

    def cancel(self):
        if self.kitchen_status in (self.KitchenStatus.SERVED, self.KitchenStatus.CANCELLED):
            raise ValidationError("Cannot cancel an item that has already been served or cancelled.")
        self.kitchen_status = self.KitchenStatus.CANCELLED
        self.save(update_fields=["kitchen_status"])
        broadcast_kitchen_update(self)


class Refund(BranchModel):
    """A refund against an already-paid order -- distinct from Order.cancel(),
    which only applies to an order that hasn't been paid yet. The food/drink
    has typically already been served by the time a refund is requested, so
    unlike Wastage this does NOT restore stock; it's purely a financial
    reversal, requiring Manager approval (readme: Manager can "Approve
    refunds") the same way Wastage/Complimentary meals do.
    """

    class Reason(models.TextChoices):
        WRONG_ORDER = "wrong_order", "Wrong order"
        QUALITY_ISSUE = "quality_issue", "Quality issue"
        CUSTOMER_COMPLAINT = "customer_complaint", "Customer complaint"
        DUPLICATE_PAYMENT = "duplicate_payment", "Duplicate payment"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="refunds")
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    reason = models.CharField(max_length=30, choices=Reason.choices)
    notes = models.CharField(max_length=255, blank=True)
    requested_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="refunds_requested"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    approved_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="refunds_approved"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Refund {self.amount} for {self.order} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if self._state.adding:
            if self.order.status != Order.Status.PAID:
                raise ValidationError("Refunds can only be requested for a paid order.")
            already_approved = Refund.unscoped.filter(order=self.order, status=self.Status.APPROVED).aggregate(
                total=models.Sum("amount")
            )["total"] or Decimal("0.00")
            remaining = self.order.total - already_approved
            if self.amount > remaining:
                raise ValidationError(
                    f"Refund amount exceeds the order's remaining refundable balance of {remaining}."
                )
        super().save(*args, **kwargs)

    def approve(self, actor):
        if self.status != self.Status.PENDING:
            raise ValidationError("Only a pending refund can be approved.")
        self.status = self.Status.APPROVED
        self.approved_by = actor
        self.approved_at = timezone.now()
        self.save(update_fields=["status", "approved_by", "approved_at"])
        AuditLog.objects.create(
            tenant=self.tenant, branch=self.branch, actor=actor, action="refund.approved", object_repr=str(self)
        )

    def reject(self, actor):
        if self.status != self.Status.PENDING:
            raise ValidationError("Only a pending refund can be rejected.")
        self.status = self.Status.REJECTED
        self.approved_by = actor
        self.approved_at = timezone.now()
        self.save(update_fields=["status", "approved_by", "approved_at"])
        AuditLog.objects.create(
            tenant=self.tenant, branch=self.branch, actor=actor, action="refund.rejected", object_repr=str(self)
        )
