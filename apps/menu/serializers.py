from rest_framework import serializers

from .models import Category, MenuItem


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "sort_order", "is_active"]


class MenuItemSerializer(serializers.ModelSerializer):
    profit_margin = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    vat_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    price_including_vat = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = MenuItem
        fields = [
            "id",
            "category",
            "name",
            "description",
            "selling_price",
            "cost_price",
            "vat_rate",
            "prep_time_minutes",
            "requires_kitchen",
            "is_available",
            "profit_margin",
            "vat_amount",
            "price_including_vat",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
