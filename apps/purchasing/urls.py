from rest_framework.routers import DefaultRouter

from .views import PurchaseOrderViewSet, SupplierLedgerEntryViewSet, SupplierViewSet

router = DefaultRouter()
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("ledger-entries", SupplierLedgerEntryViewSet, basename="supplierledgerentry")
router.register("orders", PurchaseOrderViewSet, basename="purchaseorder")

urlpatterns = router.urls
