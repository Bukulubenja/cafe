from rest_framework import serializers

from .models import NotificationLog


class NotificationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationLog
        fields = [
            "id",
            "notification_type",
            "recipient_phone",
            "message",
            "status",
            "object_repr",
            "created_at",
        ]
        read_only_fields = fields
