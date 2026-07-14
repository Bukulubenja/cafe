from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.accounts.permissions import IsManagerOrAbove
from apps.core.utils import resolve_acting_branch

from .models import PayrollRun, SalaryRecord
from .serializers import PayrollRunSerializer, ProcessPayrollSerializer, SalaryRecordSerializer


class SalaryRecordViewSet(viewsets.ModelViewSet):
    serializer_class = SalaryRecordSerializer
    permission_classes = [IsManagerOrAbove]

    def get_queryset(self):
        return SalaryRecord.objects.select_related("staff").all()

    def perform_create(self, serializer):
        user = self.request.user
        branch = resolve_acting_branch(user, self.request.data)
        serializer.save(created_by=user, tenant=branch.tenant, branch=branch)


class PayrollRunViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Payroll runs are immutable once processed -- no update/delete."""

    serializer_class = PayrollRunSerializer
    permission_classes = [IsManagerOrAbove]

    def get_queryset(self):
        return PayrollRun.objects.select_related("processed_by").prefetch_related("lines__staff")

    def create(self, request, *args, **kwargs):
        serializer = ProcessPayrollSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        branch = resolve_acting_branch(request.user, request.data)

        try:
            run = PayrollRun.process(branch, actor=request.user, **serializer.validated_data)
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages if hasattr(exc, "messages") else str(exc))

        return Response(PayrollRunSerializer(run).data, status=status.HTTP_201_CREATED)
