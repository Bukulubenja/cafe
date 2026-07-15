from rest_framework import serializers

from apps.menu.models import MenuItem

from .models import Order, OrderItem, Refund, Table


class TableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Table
        fields = ["id", "name", "capacity", "status"]


class OrderItemCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ["id", "menu_item", "quantity", "notes"]

    def validate_menu_item(self, value):
        if not value.is_available:
            raise serializers.ValidationError("This menu item is not currently available.")
        return value


class OrderItemSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source="menu_item.name", read_only=True)
    line_subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    line_vat = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "menu_item",
            "menu_item_name",
            "quantity",
            "unit_price",
            "vat_rate",
            "requires_kitchen",
            "kitchen_status",
            "notes",
            "line_subtotal",
            "line_vat",
            "started_cooking_at",
            "ready_at",
            "served_at",
            "client_id",
        ]
        read_only_fields = [
            "unit_price",
            "vat_rate",
            "requires_kitchen",
            "kitchen_status",
            "started_cooking_at",
            "ready_at",
            "served_at",
            "client_id",
        ]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    vat_total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    created_by_name = serializers.CharField(source="created_by.email", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "table",
            "order_type",
            "status",
            "payment_method",
            "created_by",
            "created_by_name",
            "customer",
            "opened_at",
            "closed_at",
            "items",
            "subtotal",
            "vat_total",
            "total",
            "client_id",
        ]
        read_only_fields = ["status", "payment_method", "created_by", "opened_at", "closed_at", "client_id"]


class PayOrderSerializer(serializers.Serializer):
    payment_method = serializers.ChoiceField(choices=Order.PaymentMethod.choices)


class RefundSerializer(serializers.ModelSerializer):
    order_total = serializers.DecimalField(source="order.total", max_digits=10, decimal_places=2, read_only=True)
    requested_by_email = serializers.CharField(source="requested_by.email", read_only=True, default=None)
    approved_by_email = serializers.CharField(source="approved_by.email", read_only=True, default=None)

    class Meta:
        model = Refund
        fields = [
            "id",
            "order",
            "order_total",
            "amount",
            "reason",
            "notes",
            "requested_by",
            "requested_by_email",
            "status",
            "approved_by",
            "approved_by_email",
            "approved_at",
            "created_at",
        ]
        read_only_fields = ["requested_by", "status", "approved_by", "approved_at", "created_at"]


class KitchenTicketSerializer(serializers.ModelSerializer):
    """Kitchen-facing view: no prices, per the readme's 'chef cannot view prices' rule."""

    table = serializers.CharField(source="order.table.name", default=None, read_only=True)
    order_id = serializers.IntegerField(read_only=True)
    menu_item_name = serializers.CharField(source="menu_item.name", read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "order_id",
            "table",
            "menu_item_name",
            "quantity",
            "notes",
            "kitchen_status",
            "started_cooking_at",
            "ready_at",
        ]
