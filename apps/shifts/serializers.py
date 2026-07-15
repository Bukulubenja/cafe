from rest_framework import serializers

from .models import Shift


class ShiftSerializer(serializers.ModelSerializer):
    staff_email = serializers.CharField(source="staff.email", read_only=True)
    closed_by_email = serializers.CharField(source="closed_by.email", read_only=True, default=None)
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = Shift
        fields = [
            "id",
            "staff",
            "staff_email",
            "opened_at",
            "closed_at",
            "closed_by",
            "closed_by_email",
            "is_open",
            "notes",
        ]
        read_only_fields = ["staff", "opened_at", "closed_at", "closed_by"]
