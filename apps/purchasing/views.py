from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.accounts.permissions import IsManagerOrAbove
from apps.core.utils import resolve_acting_branch

from .models import PurchaseOrder, PurchaseOrderLine, Supplier, SupplierLedgerEntry
from .serializers import (
    PurchaseOrderLineCreateSerializer,
    PurchaseOrderLineSerializer,
    PurchaseOrderSerializer,
    SupplierLedgerEntrySerializer,
    SupplierPaymentSerializer,
    SupplierSerializer,
)


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except DjangoValidationError as exc:
        raise DRFValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)


class SupplierViewSet(viewsets.ModelViewSet):
    serializer_class = SupplierSerializer
    permission_classes = [IsManagerOrAbove]

    def get_queryset(self):
        return Supplier.objects.all()

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        supplier = self.get_object()
        serializer = SupplierPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = _run(
            supplier.pay,
            serializer.validated_data["amount"],
            actor=request.user,
            notes=serializer.validated_data["notes"],
        )
        return Response(SupplierLedgerEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class SupplierLedgerEntryViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Read-only: entries are only ever created via PurchaseOrder.receive() or Supplier.pay()."""

    serializer_class = SupplierLedgerEntrySerializer
    permission_classes = [IsManagerOrAbove]

    def get_queryset(self):
        return SupplierLedgerEntry.objects.select_related("supplier", "purchase_order", "created_by").all()


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    serializer_class = PurchaseOrderSerializer
    permission_classes = [IsManagerOrAbove]

    def get_queryset(self):
        return PurchaseOrder.objects.select_related("supplier", "created_by", "approved_by").prefetch_related(
            "lines__ingredient"
        )

    def perform_create(self, serializer):
        user = self.request.user
        branch = resolve_acting_branch(user, self.request.data)
        serializer.save(created_by=user, tenant=branch.tenant, branch=branch)

    @action(detail=True, methods=["post"], url_path="lines")
    def add_line(self, request, pk=None):
        order = self.get_object()
        if order.status != PurchaseOrder.Status.PENDING:
            raise DRFValidationError("Cannot add lines to a purchase order that is not pending.")
        serializer = PurchaseOrderLineCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        line = PurchaseOrderLine.objects.create(
            purchase_order=order, tenant=order.tenant, branch=order.branch, **serializer.validated_data
        )
        return Response(PurchaseOrderLineSerializer(line).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        order = self.get_object()
        _run(order.receive, actor=request.user)
        return Response(PurchaseOrderSerializer(order).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        _run(order.cancel, actor=request.user)
        return Response(PurchaseOrderSerializer(order).data)
