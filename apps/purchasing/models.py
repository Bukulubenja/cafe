from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from apps.core.models import AuditLog, BranchModel, TenantModel
from apps.inventory.models import Ingredient, StockItem


class Supplier(TenantModel):
    """A goods supplier, shared across a café's branches.

    `balance` (what the café owes this supplier) is computed from its
    ledger of purchase/payment entries rather than a stored counter, so it
    can never drift out of sync -- same pattern as Customer/LoyaltyTransaction.
    """

    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_supplier_name_per_cafe"),
        ]

    def __str__(self):
        return self.name

    @property
    def balance(self):
        purchases = self.ledger_entries.filter(entry_type=SupplierLedgerEntry.EntryType.PURCHASE).aggregate(
            total=models.Sum("amount")
        )["total"] or 0
        payments = self.ledger_entries.filter(entry_type=SupplierLedgerEntry.EntryType.PAYMENT).aggregate(
            total=models.Sum("amount")
        )["total"] or 0
        return purchases - payments

    def pay(self, amount, actor=None, notes=""):
        if amount <= 0:
            raise ValidationError("Payment amount must be positive.")
        entry = SupplierLedgerEntry.objects.create(
            supplier=self,
            entry_type=SupplierLedgerEntry.EntryType.PAYMENT,
            amount=amount,
            created_by=actor,
            notes=notes,
            tenant=self.tenant,
        )
        AuditLog.objects.create(
            tenant=self.tenant, actor=actor, action="supplier.paid", object_repr=f"{self}: {amount}"
        )
        return entry


class SupplierLedgerEntry(TenantModel):
    class EntryType(models.TextChoices):
        PURCHASE = "purchase", "Purchase"
        PAYMENT = "payment", "Payment"

    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="ledger_entries")
    entry_type = models.CharField(max_length=10, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    purchase_order = models.ForeignKey(
        "PurchaseOrder", on_delete=models.SET_NULL, null=True, blank=True, related_name="ledger_entries"
    )
    created_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_entry_type_display()} {self.amount} - {self.supplier}"


class PurchaseOrder(BranchModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="purchase_orders_created"
    )
    approved_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="purchase_orders_approved"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"PO #{self.pk} - {self.supplier} ({self.get_status_display()})"

    @property
    def total(self):
        return sum((line.line_total for line in self.lines.all()), 0)

    def receive(self, actor=None):
        if self.status != self.Status.PENDING:
            raise ValidationError("Only a pending purchase order can be received.")

        with transaction.atomic():
            for line in self.lines.select_related("ingredient"):
                stock_item = (
                    StockItem.unscoped.select_for_update()
                    .filter(branch=self.branch, ingredient=line.ingredient)
                    .first()
                )
                if stock_item is None:
                    stock_item = StockItem.unscoped.create(
                        tenant=self.tenant, branch=self.branch, ingredient=line.ingredient, quantity_on_hand=0
                    )
                stock_item.quantity_on_hand += line.quantity
                stock_item.save(update_fields=["quantity_on_hand", "updated_at"])

            self.status = self.Status.RECEIVED
            self.approved_by = actor
            self.approved_at = timezone.now()
            self.save(update_fields=["status", "approved_by", "approved_at"])

            SupplierLedgerEntry.objects.create(
                supplier=self.supplier,
                entry_type=SupplierLedgerEntry.EntryType.PURCHASE,
                amount=self.total,
                purchase_order=self,
                created_by=actor,
                tenant=self.tenant,
            )

        AuditLog.objects.create(
            tenant=self.tenant,
            branch=self.branch,
            actor=actor,
            action="purchase_order.received",
            object_repr=str(self),
        )

    def cancel(self, actor=None):
        if self.status != self.Status.PENDING:
            raise ValidationError("Only a pending purchase order can be cancelled.")
        self.status = self.Status.CANCELLED
        self.save(update_fields=["status"])
        AuditLog.objects.create(
            tenant=self.tenant,
            branch=self.branch,
            actor=actor,
            action="purchase_order.cancelled",
            object_repr=str(self),
        )


class PurchaseOrderLine(BranchModel):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name="purchase_order_lines")
    quantity = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(0)])
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.quantity}{self.ingredient.unit} {self.ingredient.name}"

    @property
    def line_total(self):
        return self.quantity * self.unit_cost
