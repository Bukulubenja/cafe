from django.contrib import admin

from .models import Shift


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ("staff", "branch", "opened_at", "closed_at", "closed_by")
    list_filter = ("branch",)
