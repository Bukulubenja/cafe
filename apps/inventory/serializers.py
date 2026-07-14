from rest_framework import serializers

from .models import Ingredient, RecipeItem, StockItem


class IngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ingredient
        fields = ["id", "name", "category", "unit", "is_active"]


class StockItemSerializer(serializers.ModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    unit = serializers.CharField(source="ingredient.unit", read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = StockItem
        fields = [
            "id",
            "ingredient",
            "ingredient_name",
            "unit",
            "quantity_on_hand",
            "minimum_quantity",
            "supplier_name",
            "buying_price",
            "batch_number",
            "expiry_date",
            "is_low_stock",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]


class RecipeItemSerializer(serializers.ModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    unit = serializers.CharField(source="ingredient.unit", read_only=True)

    class Meta:
        model = RecipeItem
        fields = ["id", "menu_item", "ingredient", "ingredient_name", "unit", "quantity_required"]
