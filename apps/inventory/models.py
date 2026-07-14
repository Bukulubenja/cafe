from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import BranchModel, TenantModel
from apps.menu.models import MenuItem
from apps.notifications.services import send_low_stock_alert


class Ingredient(TenantModel):
    """A raw-stock ingredient type, shared across a café's branches (e.g.
    Rice, Chicken, Cooking Oil). Actual on-hand quantity is per-branch,
    tracked on StockItem.
    """

    class Category(models.TextChoices):
        KITCHEN = "kitchen", "Kitchen"
        BAR = "bar", "Bar"
        CLEANING = "cleaning", "Cleaning"
        PACKAGING = "packaging", "Packaging"
        CONSUMABLES = "consumables", "Consumables"

    class Unit(models.TextChoices):
        GRAM = "g", "Grams"
        KILOGRAM = "kg", "Kilograms"
        MILLILITRE = "ml", "Millilitres"
        LITRE = "l", "Litres"
        PIECE = "piece", "Piece"

    name = models.CharField(max_length=150)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.KITCHEN)
    unit = models.CharField(max_length=10, choices=Unit.choices, default=Unit.PIECE)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_ingredient_name_per_cafe"),
        ]

    def __str__(self):
        return self.name


class StockItem(BranchModel):
    """Per-branch on-hand quantity of one Ingredient."""

    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name="stock_items")
    quantity_on_hand = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    minimum_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    supplier_name = models.CharField(max_length=150, blank=True)
    buying_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    batch_number = models.CharField(max_length=100, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ingredient__name"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "ingredient"], name="unique_stock_item_per_branch"),
        ]

    def __str__(self):
        return f"{self.ingredient.name} @ {self.branch}"

    @property
    def is_low_stock(self):
        return self.quantity_on_hand <= self.minimum_quantity

    def save(self, *args, **kwargs):
        was_low_stock = False
        if self.pk:
            previous = StockItem.unscoped.filter(pk=self.pk).values("quantity_on_hand", "minimum_quantity").first()
            if previous:
                was_low_stock = previous["quantity_on_hand"] <= previous["minimum_quantity"]

        super().save(*args, **kwargs)

        # Alert only on the transition into low stock, not on every save
        # while it stays there (e.g. several small POS deductions in a
        # row) -- otherwise every sale after the first would spam the alert.
        if self.is_low_stock and not was_low_stock:
            send_low_stock_alert(self)


class RecipeItem(TenantModel):
    """One ingredient line in a MenuItem's recipe -- how much of `ingredient`
    (in its own unit) is consumed each time one unit of `menu_item` is sold.
    """

    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name="recipe_items")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name="used_in_recipes")
    quantity_required = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(0)])

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["menu_item", "ingredient"], name="unique_ingredient_per_menu_item_recipe"
            ),
        ]

    def __str__(self):
        return f"{self.menu_item.name}: {self.quantity_required}{self.ingredient.unit} {self.ingredient.name}"
