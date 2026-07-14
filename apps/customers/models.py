from decimal import Decimal

from django.db import models

from apps.core.models import BranchModel, TenantModel
from apps.menu.models import MenuItem


class Customer(TenantModel):
    """A café's customer, shared across all of its branches.

    `visit_count`/`total_spent`/`loyalty_points_balance` are computed from
    actual order/transaction history rather than stored counters, so they
    can never drift out of sync with reality.
    """

    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    favorite_item = models.ForeignKey(
        MenuItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="favorited_by_customers"
    )
    birthday = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "phone"], name="unique_customer_phone_per_cafe"),
        ]

    def __str__(self):
        return f"{self.name} ({self.phone})"

    @property
    def visit_count(self):
        # `orders` is Order's related_name for its `customer` FK (apps.pos).
        # Not imported directly here to avoid a customers <-> pos import cycle.
        return self.orders.filter(status="paid").count()

    @property
    def total_spent(self):
        return sum((order.total for order in self.orders.filter(status="paid")), Decimal("0.00"))

    @property
    def loyalty_points_balance(self):
        earned = self.loyalty_transactions.filter(transaction_type=LoyaltyTransaction.Type.EARN).aggregate(
            total=models.Sum("points")
        )["total"] or 0
        redeemed = self.loyalty_transactions.filter(transaction_type=LoyaltyTransaction.Type.REDEEM).aggregate(
            total=models.Sum("points")
        )["total"] or 0
        return earned - redeemed


class LoyaltyTransaction(BranchModel):
    """One entry in a customer's points ledger -- an earn from a paid order,
    or a redemption for a menu item. Stored as a ledger (not a mutable
    counter) so the balance can never silently drift and every change stays
    auditable.
    """

    class Type(models.TextChoices):
        EARN = "earn", "Earn"
        REDEEM = "redeem", "Redeem"

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="loyalty_transactions")
    transaction_type = models.CharField(max_length=10, choices=Type.choices)
    points = models.PositiveIntegerField()
    order = models.ForeignKey(
        "pos.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="loyalty_transactions"
    )
    menu_item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_transaction_type_display()} {self.points}pts - {self.customer}"
