from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import UserSerializer


class MeView(APIView):
    """Returns the logged-in user plus the tenant/branch context resolved
    by TenantMiddleware -- useful for verifying tenant scoping end to end.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = UserSerializer(request.user).data
        data["resolved_tenant_id"] = request.tenant.id if getattr(request, "tenant", None) else None
        data["resolved_branch_id"] = request.branch.id if getattr(request, "branch", None) else None
        return Response(data)
