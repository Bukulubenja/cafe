from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import BranchModel


class Expense(BranchModel):
    """A non-purchase operating cost (readme: electricity, water, fuel,
    rent, internet, gas, cleaning, repairs) -- tracked separately from
    Purchasing, which is specifically for stock/ingredients.
    """

    class Category(models.TextChoices):
        ELECTRICITY = "electricity", "Electricity"
        WATER = "water", "Water"
        FUEL = "fuel", "Fuel"
        RENT = "rent", "Rent"
        INTERNET = "internet", "Internet"
        GAS = "gas", "Gas"
        CLEANING = "cleaning", "Cleaning"
        REPAIRS = "repairs", "Repairs"
        OTHER = "other", "Other"

    category = models.CharField(max_length=20, choices=Category.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    date = models.DateField(default=timezone.localdate)
    notes = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.get_category_display()}: {self.amount} ({self.date})"
