from decimal import Decimal

from django.test import TestCase, override_settings

from apps.core.context import set_current_branch, set_current_tenant
from apps.inventory.models import Ingredient, RecipeItem, StockItem
from apps.menu.models import Category, MenuItem
from apps.purchasing.models import PurchaseOrder, PurchaseOrderLine, Supplier
from apps.tenants.models import Branch, Cafe

from .models import NotificationLog
from .services import send_daily_summary, send_low_stock_alert, send_purchase_order, send_receipt


class _FailingBackend:
    def send(self, to_phone, message):
        raise ConnectionError("simulated network failure")


class _RejectingBackend:
    def send(self, to_phone, message):
        return False


class NotificationServiceTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")

    def test_console_backend_default_logs_as_sent(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        from apps.customers.models import Customer
        from apps.pos.models import Order, OrderItem, Table

        category = Category.objects.create(name="Lunch")
        item = MenuItem.objects.create(category=category, name="Tea", selling_price=Decimal("2000"))
        table = Table.objects.create(name="T1")
        customer = Customer.objects.create(name="Amina", phone="0700111222")
        order = Order.objects.create(table=table, customer=customer)
        OrderItem.objects.create(order=order, menu_item=item, quantity=1)
        set_current_tenant(None)
        set_current_branch(None)

        log = send_receipt(order)
        self.assertIsNotNone(log)
        self.assertEqual(log.status, NotificationLog.Status.SENT)
        self.assertEqual(log.recipient_phone, "0700111222")
        self.assertEqual(log.notification_type, NotificationLog.NotificationType.RECEIPT)

    def test_no_customer_is_a_noop(self):
        from apps.pos.models import Order, Table

        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        table = Table.objects.create(name="T1")
        order = Order.objects.create(table=table)  # no customer
        set_current_tenant(None)
        set_current_branch(None)

        self.assertIsNone(send_receipt(order))
        self.assertEqual(NotificationLog.objects.count(), 0)

    @override_settings(WHATSAPP_BACKEND="apps.notifications.tests._FailingBackend")
    def test_backend_exception_is_caught_and_logged_as_failed(self):
        from apps.customers.models import Customer
        from apps.pos.models import Order, OrderItem, Table

        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        category = Category.objects.create(name="Lunch")
        item = MenuItem.objects.create(category=category, name="Tea", selling_price=Decimal("2000"))
        table = Table.objects.create(name="T1")
        customer = Customer.objects.create(name="Amina", phone="0700111222")
        order = Order.objects.create(table=table, customer=customer)
        OrderItem.objects.create(order=order, menu_item=item, quantity=1)
        set_current_tenant(None)
        set_current_branch(None)

        log = send_receipt(order)  # should not raise
        self.assertEqual(log.status, NotificationLog.Status.FAILED)

    @override_settings(WHATSAPP_BACKEND="apps.notifications.tests._RejectingBackend")
    def test_backend_returning_false_is_logged_as_failed(self):
        from apps.customers.models import Customer
        from apps.pos.models import Order, OrderItem, Table

        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        category = Category.objects.create(name="Lunch")
        item = MenuItem.objects.create(category=category, name="Tea", selling_price=Decimal("2000"))
        table = Table.objects.create(name="T1")
        customer = Customer.objects.create(name="Amina", phone="0700111222")
        order = Order.objects.create(table=table, customer=customer)
        OrderItem.objects.create(order=order, menu_item=item, quantity=1)
        set_current_tenant(None)
        set_current_branch(None)

        log = send_receipt(order)
        self.assertEqual(log.status, NotificationLog.Status.FAILED)

    def test_low_stock_alert_prefers_manager_falls_back_to_owner(self):
        from apps.accounts.models import User

        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        chicken = Ingredient.objects.create(name="Chicken", unit=Ingredient.Unit.PIECE)
        stock = StockItem.objects.create(
            ingredient=chicken, quantity_on_hand=Decimal("1"), minimum_quantity=Decimal("5")
        )
        set_current_tenant(None)
        set_current_branch(None)

        # no manager phone yet -> falls back to owner
        owner = User.objects.create_user(
            email="owner@javas.co", password="pw12345!", role=User.Role.OWNER, cafe=self.cafe, phone="0700000001"
        )
        logs = send_low_stock_alert(stock)
        self.assertEqual([l.recipient_phone for l in logs], ["0700000001"])

        # once a manager has a phone, they take priority over the owner
        User.objects.create_user(
            email="manager@javas.co",
            password="pw12345!",
            role=User.Role.MANAGER,
            cafe=self.cafe,
            branch=self.branch,
            phone="0700000002",
        )
        logs = send_low_stock_alert(stock)
        self.assertEqual([l.recipient_phone for l in logs], ["0700000002"])

    def test_send_purchase_order_requires_supplier_phone(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        supplier = Supplier.objects.create(name="Fresh Cuts")  # no phone
        order = PurchaseOrder.objects.create(supplier=supplier)
        chicken = Ingredient.objects.create(name="Chicken", unit=Ingredient.Unit.PIECE)
        PurchaseOrderLine.objects.create(purchase_order=order, ingredient=chicken, quantity=Decimal("10"), unit_cost=Decimal("8000"))
        set_current_tenant(None)
        set_current_branch(None)

        self.assertIsNone(send_purchase_order(order))

        supplier.phone = "0700333444"
        supplier.save(update_fields=["phone"])
        log = send_purchase_order(order)
        self.assertIsNotNone(log)
        self.assertIn("Chicken", log.message)

    def test_send_daily_summary_creates_one_log_per_recipient(self):
        from apps.closing.models import DailyClosing
        from apps.accounts.models import User

        User.objects.create_user(
            email="manager@javas.co",
            password="pw12345!",
            role=User.Role.MANAGER,
            cafe=self.cafe,
            branch=self.branch,
            phone="0700555666",
        )
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        closing = DailyClosing.objects.create(
            tenant=self.cafe, branch=self.branch, cash_counted=Decimal("0"), cash_expected=Decimal("0")
        )
        set_current_tenant(None)
        set_current_branch(None)

        logs = send_daily_summary(closing)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].notification_type, NotificationLog.NotificationType.DAILY_SUMMARY)
