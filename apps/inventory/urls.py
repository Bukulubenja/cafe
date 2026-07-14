from rest_framework.routers import DefaultRouter

from .views import IngredientViewSet, RecipeItemViewSet, StockItemViewSet

router = DefaultRouter()
router.register("ingredients", IngredientViewSet, basename="ingredient")
router.register("stock", StockItemViewSet, basename="stockitem")
router.register("recipe-items", RecipeItemViewSet, basename="recipeitem")

urlpatterns = router.urls
