from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, MenuItemViewSet

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("items", MenuItemViewSet, basename="menuitem")

urlpatterns = router.urls
