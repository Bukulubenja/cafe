from django.contrib import admin

from .models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("notification_type", "recipient_phone", "status", "branch", "created_at")
    list_filter = ("branch", "notification_type", "status")
