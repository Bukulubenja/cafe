from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.accounts.permissions import IsManagerOrAbove
from apps.core.utils import resolve_acting_branch

from .models import DailyClosing
from .serializers import CloseDaySerializer, DailyClosingSerializer


class DailyClosingViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Financial closing records are immutable once created -- no update or
    delete, matching real end-of-day reconciliation.
    """

    serializer_class = DailyClosingSerializer
    permission_classes = [IsManagerOrAbove]

    def get_queryset(self):
        return DailyClosing.objects.select_related("closed_by").all()

    def create(self, request, *args, **kwargs):
        serializer = CloseDaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        branch = resolve_acting_branch(request.user, request.data)

        try:
            closing = DailyClosing.close_day(branch, actor=request.user, **serializer.validated_data)
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages if hasattr(exc, "messages") else str(exc))

        return Response(DailyClosingSerializer(closing).data, status=status.HTTP_201_CREATED)
