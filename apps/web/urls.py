from django.urls import path

from . import views

app_name = "web"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("", views.home, name="home"),
    path("tables/", views.tables, name="tables"),
    path("tables/<int:table_id>/order/", views.order_for_table, name="order_for_table"),
    path("orders/new-takeaway/", views.new_takeaway_order, name="new_takeaway"),
    path("orders/<int:order_id>/", views.order_detail, name="order_detail"),
    path("orders/<int:order_id>/add-item/", views.order_add_item, name="order_add_item"),
    path("orders/<int:order_id>/pay/", views.order_pay, name="order_pay"),
    path("orders/<int:order_id>/cancel/", views.order_cancel, name="order_cancel"),
    path("kitchen/", views.kitchen, name="kitchen"),
]
