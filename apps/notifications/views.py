from rest_framework import mixins, viewsets

from apps.accounts.permissions import IsManagerOrAbove

from .models import NotificationLog
from .serializers import NotificationLogSerializer


class NotificationLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Read-only: entries are only ever created by apps.notifications.services."""

    serializer_class = NotificationLogSerializer
    permission_classes = [IsManagerOrAbove]

    def get_queryset(self):
        return NotificationLog.objects.all()
