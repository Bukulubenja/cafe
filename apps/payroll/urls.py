from rest_framework.routers import DefaultRouter

from .views import PayrollRunViewSet, SalaryRecordViewSet

router = DefaultRouter()
router.register("salary-records", SalaryRecordViewSet, basename="salaryrecord")
router.register("runs", PayrollRunViewSet, basename="payrollrun")

urlpatterns = router.urls
