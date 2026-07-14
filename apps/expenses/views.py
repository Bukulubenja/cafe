from rest_framework import viewsets

from apps.accounts.permissions import IsManagerOrAbove
from apps.core.utils import resolve_acting_branch

from .models import Expense
from .serializers import ExpenseSerializer


class ExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseSerializer
    permission_classes = [IsManagerOrAbove]

    def get_queryset(self):
        return Expense.objects.all()

    def perform_create(self, serializer):
        user = self.request.user
        branch = resolve_acting_branch(user, self.request.data)
        serializer.save(recorded_by=user, tenant=branch.tenant, branch=branch)
