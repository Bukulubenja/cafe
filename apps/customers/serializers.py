from rest_framework import serializers

from .models import Customer, LoyaltyTransaction


class CustomerSerializer(serializers.ModelSerializer):
    favorite_item_name = serializers.CharField(source="favorite_item.name", read_only=True, default=None)
    visit_count = serializers.IntegerField(read_only=True)
    total_spent = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    loyalty_points_balance = serializers.IntegerField(read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "favorite_item",
            "favorite_item_name",
            "birthday",
            "visit_count",
            "total_spent",
            "loyalty_points_balance",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class LoyaltyTransactionSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source="menu_item.name", read_only=True, default=None)
    created_by_email = serializers.CharField(source="created_by.email", read_only=True, default=None)

    class Meta:
        model = LoyaltyTransaction
        fields = [
            "id",
            "customer",
            "transaction_type",
            "points",
            "order",
            "menu_item",
            "menu_item_name",
            "created_by",
            "created_by_email",
            "notes",
            "created_at",
        ]
        read_only_fields = fields


class RedeemSerializer(serializers.Serializer):
    menu_item = serializers.IntegerField()
