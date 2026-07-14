from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.accounts.models import User
from apps.accounts.permissions import IsManagerOrAbove
from apps.core.utils import resolve_acting_branch

from .models import FeedingRecord, FeedingSlot
from .permissions import FeedingRecordPermission
from .serializers import FeedingRecordSerializer, FeedingSlotSerializer


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except DjangoValidationError as exc:
        raise DRFValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)


class FeedingSlotViewSet(viewsets.ModelViewSet):
    serializer_class = FeedingSlotSerializer
    permission_classes = [IsManagerOrAbove]

    def get_queryset(self):
        return FeedingSlot.objects.all()


class FeedingRecordViewSet(viewsets.ModelViewSet):
    serializer_class = FeedingRecordSerializer
    permission_classes = [FeedingRecordPermission]

    def get_queryset(self):
        qs = FeedingRecord.objects.select_related("staff", "slot", "menu_item").all()
        user = self.request.user
        if user.role not in (User.Role.OWNER, User.Role.MANAGER):
            qs = qs.filter(staff=user)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        branch = resolve_acting_branch(user, self.request.data)
        _run(serializer.save, staff=user, tenant=branch.tenant, branch=branch)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """readme's Staff Feeding reports: who ate, cost, frequency -- grouped by staff."""
        by_staff = defaultdict(lambda: {"count": 0, "total_cost": Decimal("0.00")})
        for record in self.get_queryset():
            key = record.staff.email if record.staff else "unknown"
            by_staff[key]["count"] += 1
            by_staff[key]["total_cost"] += record.unit_cost or Decimal("0.00")
        results = [{"staff": staff, **stats} for staff, stats in by_staff.items()]
        return Response(results)
