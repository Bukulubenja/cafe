from rest_framework import serializers

from .models import Expense


class ExpenseSerializer(serializers.ModelSerializer):
    recorded_by_email = serializers.CharField(source="recorded_by.email", read_only=True, default=None)

    class Meta:
        model = Expense
        fields = ["id", "category", "amount", "date", "notes", "recorded_by", "recorded_by_email", "created_at"]
        read_only_fields = ["recorded_by", "created_at"]
