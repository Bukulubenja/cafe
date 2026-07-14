from rest_framework.routers import DefaultRouter

from .views import WastageRecordViewSet

router = DefaultRouter()
router.register("records", WastageRecordViewSet, basename="wastagerecord")

urlpatterns = router.urls
