from rest_framework.routers import DefaultRouter

from .views import NotificationLogViewSet

router = DefaultRouter()
router.register("logs", NotificationLogViewSet, basename="notificationlog")

urlpatterns = router.urls
