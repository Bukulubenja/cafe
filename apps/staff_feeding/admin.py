from django.contrib import admin

from .models import FeedingRecord, FeedingSlot


@admin.register(FeedingSlot)
class FeedingSlotAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "start_time", "end_time", "is_active")
    list_filter = ("tenant", "is_active")


@admin.register(FeedingRecord)
class FeedingRecordAdmin(admin.ModelAdmin):
    list_display = ("staff", "slot", "menu_item", "branch", "date", "unit_cost")
    list_filter = ("branch", "slot")
