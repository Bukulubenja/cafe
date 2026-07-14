from django.contrib import admin

from .models import Expense


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("category", "branch", "amount", "date", "recorded_by")
    list_filter = ("branch", "category")
