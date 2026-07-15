# URL names that live under the topbar's "Manage" dropdown. Kept as one set
# here rather than each view passing an `in_manage_section` flag by hand --
# add a new screen's url_name here and its active-state highlighting and
# open-by-default behavior just work.
MANAGE_URL_NAMES = {
    "stock_list",
    "stock_new",
    "stock_adjust",
    "ingredients",
    "suppliers",
    "supplier_pay",
    "purchase_orders",
    "purchase_order_new",
    "purchase_order_detail",
    "purchase_order_add_line",
    "purchase_order_receive",
    "purchase_order_cancel",
    "purchase_order_notify_supplier",
    "feeding_slots",
}


def manage_section(request):
    resolver_match = getattr(request, "resolver_match", None)
    url_name = getattr(resolver_match, "url_name", None)
    return {"in_manage_section": url_name in MANAGE_URL_NAMES}
