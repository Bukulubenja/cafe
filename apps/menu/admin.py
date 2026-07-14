from django.contrib import admin

from .models import Category, MenuItem


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "sort_order", "is_active")
    list_filter = ("tenant", "is_active")


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "tenant", "selling_price", "cost_price", "is_available")
    list_filter = ("tenant", "category", "is_available", "requires_kitchen")
    search_fields = ("name",)
