from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TenantModel


class Category(TenantModel):
    """A menu category shared across all of a café's branches (e.g.
    Breakfast, Lunch, Sauces, Fast Foods, Drinks, Alcohol, Bakery, Desserts).
    """

    name = models.CharField(max_length=100)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_category_name_per_cafe"),
        ]

    def __str__(self):
        return self.name


class MenuItem(TenantModel):
    """A sellable item on the café's shared menu.

    `is_available` is the tenant-wide switch (e.g. seasonal item removed).
    Per-branch stock-driven availability (e.g. "out of chicken today") is
    computed on demand via `is_available_at()` rather than stored, so it
    never needs to be kept in sync via signals scattered across every
    stock-mutating app (POS, wastage, comp meals, purchasing, ...).
    """

    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="items")
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    vat_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0)],
        help_text="VAT percentage, e.g. 18.00 for 18%",
    )
    prep_time_minutes = models.PositiveIntegerField(default=0)
    requires_kitchen = models.BooleanField(default=True, help_text="False for items like bottled drinks that need no preparation")
    is_available = models.BooleanField(default=True)
    points_cost = models.PositiveIntegerField(
        null=True, blank=True, help_text="Loyalty points a customer can redeem for this item; blank = not redeemable"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category__sort_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_menu_item_name_per_cafe"),
        ]

    def __str__(self):
        return self.name

    @property
    def profit_margin(self):
        return self.selling_price - self.cost_price

    @property
    def vat_amount(self):
        return (self.selling_price * self.vat_rate / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def price_including_vat(self):
        return self.selling_price + self.vat_amount

    def is_available_at(self, branch):
        """readme's Ingredient Availability differentiator: an item with no
        recipe configured is always available (matches this codebase's
        existing no-recipe-means-no-stock-constraint convention); one with
        a recipe is unavailable at `branch` if the tenant-wide switch is
        off, or if any ingredient it needs is short for even one serving.
        """
        if not self.is_available:
            return False

        # Local import: apps.inventory imports apps.menu (RecipeItem ->
        # MenuItem), so a module-level import here would be circular.
        from apps.inventory.models import StockItem

        for recipe_item in self.recipe_items.select_related("ingredient"):
            stock_item = StockItem.unscoped.filter(branch=branch, ingredient=recipe_item.ingredient).first()
            if stock_item is None or stock_item.quantity_on_hand < recipe_item.quantity_required:
                return False
        return True
