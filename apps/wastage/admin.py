from django.contrib import admin

from .models import WastageRecord


@admin.register(WastageRecord)
class WastageRecordAdmin(admin.ModelAdmin):
    list_display = ("ingredient", "branch", "quantity", "reason", "status", "recorded_by", "created_at")
    list_filter = ("branch", "reason", "status")
