from rest_framework.routers import DefaultRouter

from .views import KitchenQueueViewSet, OrderViewSet, TableViewSet

router = DefaultRouter()
router.register("tables", TableViewSet, basename="table")
router.register("orders", OrderViewSet, basename="order")
router.register("kitchen/queue", KitchenQueueViewSet, basename="kitchen-ticket")

urlpatterns = router.urls
