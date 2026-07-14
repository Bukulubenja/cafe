from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.accounts.permissions import IsManagerOrAbove
from apps.core.utils import resolve_acting_branch

from .models import ComplimentaryMeal
from .permissions import ComplimentaryMealPermission
from .serializers import ComplimentaryMealSerializer


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except DjangoValidationError as exc:
        raise DRFValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)


class ComplimentaryMealViewSet(viewsets.ModelViewSet):
    serializer_class = ComplimentaryMealSerializer
    permission_classes = [ComplimentaryMealPermission]

    def get_queryset(self):
        return ComplimentaryMeal.objects.select_related("staff", "menu_item", "requested_by", "approved_by").all()

    def perform_create(self, serializer):
        user = self.request.user
        branch = resolve_acting_branch(user, self.request.data)
        serializer.save(requested_by=user, tenant=branch.tenant, branch=branch)

    @action(detail=True, methods=["post"], permission_classes=[IsManagerOrAbove])
    def approve(self, request, pk=None):
        meal = self.get_object()
        _run(meal.approve, request.user)
        return Response(ComplimentaryMealSerializer(meal).data)

    @action(detail=True, methods=["post"], permission_classes=[IsManagerOrAbove])
    def reject(self, request, pk=None):
        meal = self.get_object()
        _run(meal.reject, request.user)
        return Response(ComplimentaryMealSerializer(meal).data)
