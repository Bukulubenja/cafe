from django.contrib import admin

from .models import DailyClosing


@admin.register(DailyClosing)
class DailyClosingAdmin(admin.ModelAdmin):
    list_display = ("branch", "date", "cash_counted", "cash_expected", "difference", "closed_by")
    list_filter = ("branch",)
    readonly_fields = ("cash_expected",)
