from django.contrib import admin

from .models import Customer, LoyaltyTransaction


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "tenant", "visit_count", "total_spent", "loyalty_points_balance")
    search_fields = ("name", "phone", "email")


@admin.register(LoyaltyTransaction)
class LoyaltyTransactionAdmin(admin.ModelAdmin):
    list_display = ("customer", "transaction_type", "points", "branch", "created_at")
    list_filter = ("branch", "transaction_type")
