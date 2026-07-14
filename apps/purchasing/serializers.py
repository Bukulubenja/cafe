from decimal import Decimal

from rest_framework import serializers

from .models import PurchaseOrder, PurchaseOrderLine, Supplier, SupplierLedgerEntry


class SupplierSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Supplier
        fields = ["id", "name", "phone", "email", "address", "balance", "created_at"]
        read_only_fields = ["created_at"]


class SupplierLedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierLedgerEntry
        fields = ["id", "supplier", "entry_type", "amount", "purchase_order", "created_by", "notes", "created_at"]
        read_only_fields = fields


class SupplierPaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    unit = serializers.CharField(source="ingredient.unit", read_only=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseOrderLine
        fields = ["id", "ingredient", "ingredient_name", "unit", "quantity", "unit_cost", "line_total"]


class PurchaseOrderSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    created_by_email = serializers.CharField(source="created_by.email", read_only=True, default=None)
    approved_by_email = serializers.CharField(source="approved_by.email", read_only=True, default=None)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            "id",
            "supplier",
            "supplier_name",
            "status",
            "created_by",
            "created_by_email",
            "approved_by",
            "approved_by_email",
            "approved_at",
            "notes",
            "lines",
            "total",
            "created_at",
        ]
        read_only_fields = ["status", "created_by", "approved_by", "approved_at", "created_at"]


class PurchaseOrderLineCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrderLine
        fields = ["ingredient", "quantity", "unit_cost"]
