from django.contrib import admin

from .models import Ingredient, RecipeItem, StockItem


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "category", "unit", "is_active")
    list_filter = ("tenant", "category", "is_active")


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ("ingredient", "branch", "quantity_on_hand", "minimum_quantity", "is_low_stock", "expiry_date")
    list_filter = ("branch", "ingredient__category")


@admin.register(RecipeItem)
class RecipeItemAdmin(admin.ModelAdmin):
    list_display = ("menu_item", "ingredient", "quantity_required")
    list_filter = ("tenant",)
