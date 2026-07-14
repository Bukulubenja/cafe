from rest_framework import viewsets

from .models import Category, MenuItem
from .permissions import MenuPermission
from .serializers import CategorySerializer, MenuItemSerializer


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [MenuPermission]

    def get_queryset(self):
        # Must be a method, not a `queryset =` class attribute: the latter
        # is evaluated once at import time, before any request context
        # exists, which would permanently bake in "no tenant filter".
        return Category.objects.all()


class MenuItemViewSet(viewsets.ModelViewSet):
    serializer_class = MenuItemSerializer
    permission_classes = [MenuPermission]

    def get_queryset(self):
        return MenuItem.objects.select_related("category").all()
