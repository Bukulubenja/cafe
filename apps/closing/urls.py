from rest_framework.routers import DefaultRouter

from .views import DailyClosingViewSet

router = DefaultRouter()
router.register("closings", DailyClosingViewSet, basename="dailyclosing")

urlpatterns = router.urls
