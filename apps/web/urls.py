from django.urls import path

from . import (
    complimentary_views,
    customer_views,
    feeding_views,
    inventory_views,
    purchasing_views,
    views,
    wastage_views,
)

app_name = "web"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("tables/", views.tables, name="tables"),
    path("tables/<int:table_id>/order/", views.order_for_table, name="order_for_table"),
    path("orders/new-takeaway/", views.new_takeaway_order, name="new_takeaway"),
    path("orders/<int:order_id>/", views.order_detail, name="order_detail"),
    path("orders/<int:order_id>/add-item/", views.order_add_item, name="order_add_item"),
    path("orders/<int:order_id>/pay/", views.order_pay, name="order_pay"),
    path("orders/<int:order_id>/cancel/", views.order_cancel, name="order_cancel"),
    path("kitchen/", views.kitchen, name="kitchen"),
    path("inventory/stock/", inventory_views.stock_list, name="stock_list"),
    path("inventory/stock/new/", inventory_views.stock_new, name="stock_new"),
    path("inventory/stock/<int:stock_item_id>/adjust/", inventory_views.stock_adjust, name="stock_adjust"),
    path("inventory/ingredients/", inventory_views.ingredients, name="ingredients"),
    path("purchasing/suppliers/", purchasing_views.suppliers, name="suppliers"),
    path("purchasing/suppliers/<int:supplier_id>/pay/", purchasing_views.supplier_pay, name="supplier_pay"),
    path("purchasing/orders/", purchasing_views.purchase_orders, name="purchase_orders"),
    path("purchasing/orders/new/", purchasing_views.purchase_order_new, name="purchase_order_new"),
    path("purchasing/orders/<int:order_id>/", purchasing_views.purchase_order_detail, name="purchase_order_detail"),
    path(
        "purchasing/orders/<int:order_id>/add-line/",
        purchasing_views.purchase_order_add_line,
        name="purchase_order_add_line",
    ),
    path(
        "purchasing/orders/<int:order_id>/receive/",
        purchasing_views.purchase_order_receive,
        name="purchase_order_receive",
    ),
    path(
        "purchasing/orders/<int:order_id>/cancel/",
        purchasing_views.purchase_order_cancel,
        name="purchase_order_cancel",
    ),
    path(
        "purchasing/orders/<int:order_id>/notify-supplier/",
        purchasing_views.purchase_order_notify_supplier,
        name="purchase_order_notify_supplier",
    ),
    path("wastage/", wastage_views.wastage_list, name="wastage_list"),
    path("wastage/<int:record_id>/approve/", wastage_views.wastage_approve, name="wastage_approve"),
    path("wastage/<int:record_id>/reject/", wastage_views.wastage_reject, name="wastage_reject"),
    path("complimentary/", complimentary_views.complimentary_list, name="complimentary_list"),
    path(
        "complimentary/<int:meal_id>/approve/",
        complimentary_views.complimentary_approve,
        name="complimentary_approve",
    ),
    path(
        "complimentary/<int:meal_id>/reject/",
        complimentary_views.complimentary_reject,
        name="complimentary_reject",
    ),
    path("feeding/", feeding_views.feeding_list, name="feeding_list"),
    path("feeding/slots/", feeding_views.feeding_slots, name="feeding_slots"),
    path("customers/", customer_views.customer_list, name="customer_list"),
    path("customers/<int:customer_id>/", customer_views.customer_detail, name="customer_detail"),
    path("customers/<int:customer_id>/redeem/", customer_views.customer_redeem, name="customer_redeem"),
]
