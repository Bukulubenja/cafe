from django.contrib import admin

from .models import ComplimentaryMeal


@admin.register(ComplimentaryMeal)
class ComplimentaryMealAdmin(admin.ModelAdmin):
    list_display = ("menu_item", "branch", "quantity", "reason", "status", "staff", "created_at")
    list_filter = ("branch", "reason", "status")
