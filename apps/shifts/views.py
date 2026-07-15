from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.accounts.models import User
from apps.core.utils import resolve_acting_branch

from .models import Shift
from .permissions import ShiftPermission
from .serializers import ShiftSerializer


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except DjangoValidationError as exc:
        raise DRFValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)


class ShiftViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Clock in/out. Immutable otherwise -- no update/delete, matching
    DailyClosing/PayrollRun's approach to accountability records.
    """

    serializer_class = ShiftSerializer
    permission_classes = [ShiftPermission]

    def get_queryset(self):
        qs = Shift.objects.select_related("staff", "closed_by").all()
        user = self.request.user
        if not (user.is_superuser or user.role in (User.Role.OWNER, User.Role.MANAGER)):
            qs = qs.filter(staff=user)
        return qs

    def create(self, request, *args, **kwargs):
        branch = resolve_acting_branch(request.user, request.data)
        shift = _run(Shift.open_for, request.user, branch)
        return Response(ShiftSerializer(shift).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        # get_queryset() already scopes non-managers to their own shifts
        # (a manager sees everyone's), so get_object() alone is enough to
        # ensure only the shift's own staff member or a manager reaches
        # here -- anyone else's attempt 404s rather than 403ing.
        shift = self.get_object()
        _run(shift.close, request.user)
        return Response(ShiftSerializer(shift).data)
