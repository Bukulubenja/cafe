from django.conf import settings
from django.utils.module_loading import import_string

from .models import NotificationLog


def _get_backend():
    backend_path = getattr(
        settings, "WHATSAPP_BACKEND", "apps.notifications.backends.ConsoleWhatsAppBackend"
    )
    return import_string(backend_path)()


def _dispatch(tenant, branch, notification_type, to_phone, message, object_repr=""):
    if not to_phone:
        return None

    backend = _get_backend()
    try:
        success = backend.send(to_phone, message)
    except Exception:
        # A notification failing must never break the real business
        # operation it's attached to (a sale, a stock update, ...) --
        # record it as failed and move on.
        success = False

    return NotificationLog.objects.create(
        tenant=tenant,
        branch=branch,
        notification_type=notification_type,
        recipient_phone=to_phone,
        message=message,
        status=NotificationLog.Status.SENT if success else NotificationLog.Status.FAILED,
        object_repr=object_repr,
    )


def _branch_alert_recipients(branch):
    """Managers at this branch, falling back to the café's Owner(s) if none
    have a phone on file."""
    from apps.accounts.models import User

    phones = list(
        User.objects.filter(cafe=branch.tenant, branch=branch, role=User.Role.MANAGER)
        .exclude(phone="")
        .values_list("phone", flat=True)
    )
    if phones:
        return phones
    return list(
        User.objects.filter(cafe=branch.tenant, role=User.Role.OWNER).exclude(phone="").values_list("phone", flat=True)
    )


def send_receipt(order):
    if not order.customer_id or not order.customer.phone:
        return None
    message = (
        f"Thank you for visiting {order.tenant.name}!\n"
        f"Order #{order.id} - {order.total} UGX\n"
        f"Paid via {order.get_payment_method_display()}."
    )
    return _dispatch(
        order.tenant, order.branch, NotificationLog.NotificationType.RECEIPT, order.customer.phone, message,
        object_repr=str(order),
    )


def send_daily_summary(closing):
    message = (
        f"Daily closing for {closing.branch.name} ({closing.date}):\n"
        f"Cash expected: {closing.cash_expected}\n"
        f"Cash counted: {closing.cash_counted}\n"
        f"Difference: {closing.difference}"
    )
    return [
        _dispatch(
            closing.tenant, closing.branch, NotificationLog.NotificationType.DAILY_SUMMARY, phone, message,
            object_repr=str(closing),
        )
        for phone in _branch_alert_recipients(closing.branch)
    ]


def send_low_stock_alert(stock_item):
    message = (
        f"Low stock alert at {stock_item.branch.name}: {stock_item.ingredient.name} is at "
        f"{stock_item.quantity_on_hand}{stock_item.ingredient.unit} "
        f"(minimum {stock_item.minimum_quantity}{stock_item.ingredient.unit})."
    )
    return [
        _dispatch(
            stock_item.tenant, stock_item.branch, NotificationLog.NotificationType.LOW_STOCK, phone, message,
            object_repr=str(stock_item),
        )
        for phone in _branch_alert_recipients(stock_item.branch)
    ]


def send_purchase_order(purchase_order):
    if not purchase_order.supplier.phone:
        return None
    lines = "\n".join(
        f"- {line.quantity}{line.ingredient.unit} {line.ingredient.name}"
        for line in purchase_order.lines.select_related("ingredient")
    )
    message = f"New purchase order from {purchase_order.tenant.name}:\n{lines}\nTotal: {purchase_order.total}"
    return _dispatch(
        purchase_order.tenant,
        purchase_order.branch,
        NotificationLog.NotificationType.PURCHASE_ORDER,
        purchase_order.supplier.phone,
        message,
        object_repr=str(purchase_order),
    )
