from rest_framework import serializers

from .models import ComplimentaryMeal


class ComplimentaryMealSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source="menu_item.name", read_only=True)
    staff_email = serializers.CharField(source="staff.email", read_only=True, default=None)
    requested_by_email = serializers.CharField(source="requested_by.email", read_only=True)
    approved_by_email = serializers.CharField(source="approved_by.email", read_only=True, default=None)
    total_cost = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = ComplimentaryMeal
        fields = [
            "id",
            "staff",
            "staff_email",
            "department",
            "menu_item",
            "menu_item_name",
            "quantity",
            "reason",
            "notes",
            "requested_by",
            "requested_by_email",
            "unit_cost",
            "total_cost",
            "status",
            "approved_by",
            "approved_by_email",
            "approved_at",
            "created_at",
        ]
        read_only_fields = ["requested_by", "unit_cost", "status", "approved_by", "approved_at", "created_at"]
