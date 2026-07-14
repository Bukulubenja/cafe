from rest_framework.routers import DefaultRouter

from .views import FeedingRecordViewSet, FeedingSlotViewSet

router = DefaultRouter()
router.register("slots", FeedingSlotViewSet, basename="feedingslot")
router.register("records", FeedingRecordViewSet, basename="feedingrecord")

urlpatterns = router.urls
