from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.tenants.models import Branch

from .models import Order, OrderItem, Table
from .permissions import CanTakePayment, KitchenPermission, OrderPermission, TablePermission
from .serializers import (
    KitchenTicketSerializer,
    OrderItemCreateSerializer,
    OrderItemSerializer,
    OrderSerializer,
    PayOrderSerializer,
    TableSerializer,
)


def _run(fn, *args, **kwargs):
    """Translate Django's ValidationError (raised by model business-logic
    methods) into DRF's, so it renders as a normal 400 API error."""
    try:
        return fn(*args, **kwargs)
    except DjangoValidationError as exc:
        raise DRFValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)


class TableViewSet(viewsets.ModelViewSet):
    serializer_class = TableSerializer
    permission_classes = [TablePermission]

    def get_queryset(self):
        # Must be a method: a `queryset =` class attribute is evaluated once
        # at import time, before any request context exists, which would
        # permanently bake in "no tenant/branch filter" for every request.
        return Table.objects.all()


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [OrderPermission]

    def get_queryset(self):
        return Order.objects.select_related("table", "created_by").prefetch_related("items__menu_item").all()

    def perform_create(self, serializer):
        user = self.request.user
        branch = user.branch
        if branch is None:
            # Only an Owner (no fixed branch) hits this: they must say which
            # branch the order belongs to; Waiters/Managers/Cashiers are
            # always pinned to one, so `branch` is filled in for them.
            branch_id = self.request.data.get("branch")
            if not branch_id:
                raise DRFValidationError(
                    {"branch": "Required: you have no fixed branch, so specify which branch this order is for."}
                )
            branch = Branch.objects.filter(pk=branch_id, tenant=user.cafe).first()
            if branch is None:
                raise DRFValidationError({"branch": "Invalid branch for this café."})

        table = serializer.validated_data.get("table")
        if table is not None and table.branch_id != branch.id:
            raise DRFValidationError({"table": "Table does not belong to the selected branch."})

        order = serializer.save(created_by=user, tenant=branch.tenant, branch=branch)
        if order.table_id:
            order.table.status = Table.Status.OCCUPIED
            order.table.save(update_fields=["status"])

    @action(detail=True, methods=["post"], url_path="items")
    def add_item(self, request, pk=None):
        order = self.get_object()
        if order.status != Order.Status.OPEN:
            raise DRFValidationError("Cannot add items to an order that is not open.")
        serializer = OrderItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Set tenant/branch explicitly from the order rather than relying on
        # ambient request context, since an Owner viewing "all branches" has
        # no single branch in context yet the item must land on the order's branch.
        item = _run(
            OrderItem.objects.create,
            order=order,
            tenant=order.tenant,
            branch=order.branch,
            **serializer.validated_data,
        )
        return Response(OrderItemSerializer(item).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], permission_classes=[CanTakePayment])
    def pay(self, request, pk=None):
        order = self.get_object()
        serializer = PayOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _run(order.mark_paid, serializer.validated_data["payment_method"], actor=request.user)
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        _run(order.cancel, actor=request.user)
        return Response(OrderSerializer(order).data)


class KitchenQueueViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Read the live kitchen queue and drive ticket status transitions.
    Poll GET /kitchen/queue/ on an interval to refresh the display.
    """

    serializer_class = KitchenTicketSerializer
    permission_classes = [KitchenPermission]

    def get_queryset(self):
        return (
            OrderItem.objects.filter(
                requires_kitchen=True,
                kitchen_status__in=[
                    OrderItem.KitchenStatus.PENDING,
                    OrderItem.KitchenStatus.COOKING,
                    OrderItem.KitchenStatus.READY,
                ],
            )
            .select_related("menu_item", "order", "order__table")
            .order_by("order__opened_at", "id")
        )

    @action(detail=True, methods=["post"], url_path="start-cooking")
    def start_cooking(self, request, pk=None):
        ticket = self.get_object()
        _run(ticket.mark_cooking)
        return Response(KitchenTicketSerializer(ticket).data)

    @action(detail=True, methods=["post"], url_path="ready")
    def ready(self, request, pk=None):
        ticket = self.get_object()
        _run(ticket.mark_ready)
        return Response(KitchenTicketSerializer(ticket).data)

    @action(detail=True, methods=["post"], url_path="served")
    def served(self, request, pk=None):
        ticket = self.get_object()
        _run(ticket.mark_served)
        return Response(KitchenTicketSerializer(ticket).data)
