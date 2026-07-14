from django.contrib import admin

from .models import Order, OrderItem, Table


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("unit_price", "vat_rate", "requires_kitchen")


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ("name", "branch", "capacity", "status")
    list_filter = ("branch", "status")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "branch", "table", "order_type", "status", "created_by", "opened_at")
    list_filter = ("branch", "status", "order_type")
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "menu_item", "quantity", "kitchen_status")
    list_filter = ("branch", "kitchen_status", "requires_kitchen")
