from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.accounts.permissions import IsManagerOrAbove
from apps.core.utils import resolve_acting_branch

from .models import WastageRecord
from .permissions import WastagePermission
from .serializers import WastageRecordSerializer


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except DjangoValidationError as exc:
        raise DRFValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)


class WastageRecordViewSet(viewsets.ModelViewSet):
    serializer_class = WastageRecordSerializer
    permission_classes = [WastagePermission]

    def get_queryset(self):
        return WastageRecord.objects.select_related("ingredient", "recorded_by", "approved_by").all()

    def perform_create(self, serializer):
        user = self.request.user
        branch = resolve_acting_branch(user, self.request.data)
        _run(serializer.save, recorded_by=user, tenant=branch.tenant, branch=branch)

    @action(detail=True, methods=["post"], permission_classes=[IsManagerOrAbove])
    def approve(self, request, pk=None):
        record = self.get_object()
        _run(record.approve, request.user)
        return Response(WastageRecordSerializer(record).data)

    @action(detail=True, methods=["post"], permission_classes=[IsManagerOrAbove])
    def reject(self, request, pk=None):
        record = self.get_object()
        _run(record.reject, request.user)
        return Response(WastageRecordSerializer(record).data)
