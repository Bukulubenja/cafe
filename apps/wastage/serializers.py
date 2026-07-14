from rest_framework import serializers

from .models import WastageRecord


class WastageRecordSerializer(serializers.ModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    unit = serializers.CharField(source="ingredient.unit", read_only=True)
    recorded_by_email = serializers.CharField(source="recorded_by.email", read_only=True)
    approved_by_email = serializers.CharField(source="approved_by.email", read_only=True)

    class Meta:
        model = WastageRecord
        fields = [
            "id",
            "ingredient",
            "ingredient_name",
            "unit",
            "quantity",
            "reason",
            "notes",
            "recorded_by",
            "recorded_by_email",
            "status",
            "approved_by",
            "approved_by_email",
            "approved_at",
            "created_at",
        ]
        read_only_fields = ["recorded_by", "status", "approved_by", "approved_at", "created_at"]
