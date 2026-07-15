from django.urls import path

from .views import BalanceSheetView, DashboardView, LossDetectionView, ProfitReportView, SalesReportView

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("balance-sheet/", BalanceSheetView.as_view(), name="balance-sheet"),
    path("sales/", SalesReportView.as_view(), name="sales-report"),
    path("profit/", ProfitReportView.as_view(), name="profit-report"),
    path("loss-detection/", LossDetectionView.as_view(), name="loss-detection"),
]
