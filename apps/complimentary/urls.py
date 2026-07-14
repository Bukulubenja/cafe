from rest_framework.routers import DefaultRouter

from .views import ComplimentaryMealViewSet

router = DefaultRouter()
router.register("meals", ComplimentaryMealViewSet, basename="complimentarymeal")

urlpatterns = router.urls
