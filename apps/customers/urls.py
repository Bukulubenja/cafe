from rest_framework.routers import DefaultRouter

from .views import CustomerViewSet, LoyaltyTransactionViewSet

router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("loyalty-transactions", LoyaltyTransactionViewSet, basename="loyaltytransaction")

urlpatterns = router.urls
