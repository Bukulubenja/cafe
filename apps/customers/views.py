from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.core.utils import resolve_acting_branch
from apps.menu.models import MenuItem

from .models import Customer, LoyaltyTransaction
from .permissions import CustomerPermission
from .serializers import CustomerSerializer, LoyaltyTransactionSerializer, RedeemSerializer
from .services import redeem_points


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except DjangoValidationError as exc:
        raise DRFValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)


class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    permission_classes = [CustomerPermission]

    def get_queryset(self):
        return Customer.objects.select_related("favorite_item").all()

    @action(detail=True, methods=["post"])
    def redeem(self, request, pk=None):
        customer = self.get_object()
        serializer = RedeemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        menu_item = get_object_or_404(MenuItem, pk=serializer.validated_data["menu_item"])
        branch = resolve_acting_branch(request.user, request.data)

        transaction_record = _run(redeem_points, customer, menu_item, branch, actor=request.user)
        return Response(LoyaltyTransactionSerializer(transaction_record).data)


class LoyaltyTransactionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Read-only: entries are only ever created by the earn/redeem services,
    never directly through the API."""

    serializer_class = LoyaltyTransactionSerializer
    permission_classes = [CustomerPermission]

    def get_queryset(self):
        return LoyaltyTransaction.objects.select_related("customer", "menu_item", "created_by").all()
