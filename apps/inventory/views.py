from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Ingredient, RecipeItem, StockItem
from .permissions import InventoryPermission
from .serializers import IngredientSerializer, RecipeItemSerializer, StockItemSerializer


class IngredientViewSet(viewsets.ModelViewSet):
    serializer_class = IngredientSerializer
    permission_classes = [InventoryPermission]

    def get_queryset(self):
        return Ingredient.objects.all()


class StockItemViewSet(viewsets.ModelViewSet):
    serializer_class = StockItemSerializer
    permission_classes = [InventoryPermission]

    def get_queryset(self):
        return StockItem.objects.select_related("ingredient").all()

    @action(detail=False, methods=["get"], url_path="low")
    def low_stock(self, request):
        low = [item for item in self.get_queryset() if item.is_low_stock]
        return Response(StockItemSerializer(low, many=True).data)


class RecipeItemViewSet(viewsets.ModelViewSet):
    serializer_class = RecipeItemSerializer
    permission_classes = [InventoryPermission]

    def get_queryset(self):
        return RecipeItem.objects.select_related("ingredient", "menu_item").all()
