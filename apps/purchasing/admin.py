from django.contrib import admin

from .models import PurchaseOrder, PurchaseOrderLine, Supplier, SupplierLedgerEntry


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "phone", "balance")
    search_fields = ("name", "phone", "email")


@admin.register(SupplierLedgerEntry)
class SupplierLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("supplier", "entry_type", "amount", "created_at")
    list_filter = ("entry_type",)


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 0


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "supplier", "branch", "status", "created_by", "created_at")
    list_filter = ("branch", "status")
    inlines = [PurchaseOrderLineInline]
