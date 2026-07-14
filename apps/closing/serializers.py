from rest_framework import serializers

from .models import DailyClosing


class DailyClosingSerializer(serializers.ModelSerializer):
    closed_by_email = serializers.CharField(source="closed_by.email", read_only=True, default=None)
    difference = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = DailyClosing
        fields = [
            "id",
            "date",
            "cash_counted",
            "cash_expected",
            "difference",
            "reason",
            "closed_by",
            "closed_by_email",
            "closed_at",
        ]
        read_only_fields = ["cash_expected", "closed_by", "closed_at"]


class CloseDaySerializer(serializers.Serializer):
    cash_counted = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    date = serializers.DateField(required=False)
