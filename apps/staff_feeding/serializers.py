from rest_framework import serializers

from .models import FeedingRecord, FeedingSlot


class FeedingSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeedingSlot
        fields = ["id", "name", "start_time", "end_time", "is_active"]


class FeedingRecordSerializer(serializers.ModelSerializer):
    staff_email = serializers.CharField(source="staff.email", read_only=True)
    slot_name = serializers.CharField(source="slot.name", read_only=True)
    menu_item_name = serializers.CharField(source="menu_item.name", read_only=True)

    class Meta:
        model = FeedingRecord
        fields = [
            "id",
            "staff",
            "staff_email",
            "slot",
            "slot_name",
            "menu_item",
            "menu_item_name",
            "date",
            "unit_cost",
            "created_at",
        ]
        read_only_fields = ["staff", "unit_cost", "created_at"]
