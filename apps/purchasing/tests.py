from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.core.context import set_current_branch, set_current_tenant
from apps.core.models import AuditLog
from apps.inventory.models import Ingredient, StockItem
from apps.tenants.models import Branch, Cafe

from .models import PurchaseOrder, PurchaseOrderLine, Supplier, SupplierLedgerEntry


class SupplierBalanceTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        set_current_tenant(self.cafe)
        self.supplier = Supplier.objects.create(name="Fresh Cuts")

    def tearDown(self):
        set_current_tenant(None)

    def test_balance_nets_purchases_and_payments(self):
        SupplierLedgerEntry.objects.create(
            supplier=self.supplier, entry_type=SupplierLedgerEntry.EntryType.PURCHASE, amount=Decimal("500000")
        )
        SupplierLedgerEntry.objects.create(
            supplier=self.supplier, entry_type=SupplierLedgerEntry.EntryType.PAYMENT, amount=Decimal("200000")
        )
        self.assertEqual(self.supplier.balance, Decimal("300000"))

    def test_pay_reduces_balance_and_logs_audit(self):
        SupplierLedgerEntry.objects.create(
            supplier=self.supplier, entry_type=SupplierLedgerEntry.EntryType.PURCHASE, amount=Decimal("100000")
        )
        self.supplier.pay(Decimal("40000"))
        self.assertEqual(self.supplier.balance, Decimal("60000"))
        self.assertTrue(AuditLog.unscoped.filter(action="supplier.paid").exists())

    def test_pay_rejects_non_positive_amount(self):
        with self.assertRaises(ValidationError):
            self.supplier.pay(Decimal("0"))


class PurchaseOrderReceiveTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)

        self.supplier = Supplier.objects.create(name="Fresh Cuts")
        self.chicken = Ingredient.objects.create(name="Chicken", unit=Ingredient.Unit.PIECE)
        self.manager = User.objects.create_user(
            email="manager@javas.co", password="pw12345!", role=User.Role.MANAGER, cafe=self.cafe, branch=self.branch
        )

    def tearDown(self):
        set_current_tenant(None)
        set_current_branch(None)

    def _make_order(self, quantity=Decimal("100"), unit_cost=Decimal("8000")):
        order = PurchaseOrder.objects.create(supplier=self.supplier)
        PurchaseOrderLine.objects.create(
            purchase_order=order, ingredient=self.chicken, quantity=quantity, unit_cost=unit_cost
        )
        return order

    def test_receive_creates_new_stock_item_when_none_exists(self):
        order = self._make_order()
        order.receive(self.manager)

        stock = StockItem.unscoped.get(branch=self.branch, ingredient=self.chicken)
        self.assertEqual(stock.quantity_on_hand, Decimal("100"))
        self.assertEqual(order.status, PurchaseOrder.Status.RECEIVED)

    def test_receive_increments_existing_stock_item(self):
        StockItem.objects.create(ingredient=self.chicken, quantity_on_hand=Decimal("20"))
        order = self._make_order(quantity=Decimal("30"))
        order.receive(self.manager)

        stock = StockItem.unscoped.get(branch=self.branch, ingredient=self.chicken)
        self.assertEqual(stock.quantity_on_hand, Decimal("50"))

    def test_receive_creates_supplier_ledger_entry_for_total(self):
        order = self._make_order(quantity=Decimal("100"), unit_cost=Decimal("8000"))
        order.receive(self.manager)

        entry = SupplierLedgerEntry.objects.get(purchase_order=order)
        self.assertEqual(entry.entry_type, SupplierLedgerEntry.EntryType.PURCHASE)
        self.assertEqual(entry.amount, Decimal("800000"))
        self.assertEqual(self.supplier.balance, Decimal("800000"))

    def test_cannot_receive_twice(self):
        order = self._make_order()
        order.receive(self.manager)
        with self.assertRaises(ValidationError):
            order.receive(self.manager)

    def test_cancel_has_no_stock_or_ledger_effect(self):
        order = self._make_order()
        order.cancel(self.manager)

        self.assertEqual(order.status, PurchaseOrder.Status.CANCELLED)
        self.assertFalse(StockItem.unscoped.filter(branch=self.branch, ingredient=self.chicken).exists())
        self.assertEqual(self.supplier.balance, 0)

    def test_cannot_receive_after_cancel(self):
        order = self._make_order()
        order.cancel(self.manager)
        with self.assertRaises(ValidationError):
            order.receive(self.manager)


class PurchasingApiTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        self.supplier = Supplier.objects.create(name="Fresh Cuts")
        self.chicken = Ingredient.objects.create(name="Chicken", unit=Ingredient.Unit.PIECE)
        set_current_tenant(None)
        set_current_branch(None)

        self.manager = User.objects.create_user(
            email="manager@javas.co", password="pw12345!", role=User.Role.MANAGER, cafe=self.cafe, branch=self.branch
        )
        self.waiter = User.objects.create_user(
            email="waiter@javas.co", password="pw12345!", role=User.Role.WAITER, cafe=self.cafe, branch=self.branch
        )
        self.client = APIClient()

    def test_manager_can_create_and_receive_waiter_cannot_access(self):
        self.client.login(email="manager@javas.co", password="pw12345!")
        resp = self.client.post("/api/purchasing/orders/", {"supplier": self.supplier.id}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        order_id = resp.data["id"]

        resp = self.client.post(
            f"/api/purchasing/orders/{order_id}/lines/",
            {"ingredient": self.chicken.id, "quantity": "50", "unit_cost": "8000"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)

        resp = self.client.post(f"/api/purchasing/orders/{order_id}/receive/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["status"], "received")

        self.client.logout()
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.get("/api/purchasing/orders/")
        self.assertEqual(resp.status_code, 403)

    def test_notify_supplier_sends_whatsapp_and_requires_at_least_one_line(self):
        from apps.notifications.models import NotificationLog

        self.supplier.phone = "0700999888"
        self.supplier.save(update_fields=["phone"])

        self.client.login(email="manager@javas.co", password="pw12345!")
        resp = self.client.post("/api/purchasing/orders/", {"supplier": self.supplier.id}, format="json")
        order_id = resp.data["id"]

        resp = self.client.post(f"/api/purchasing/orders/{order_id}/notify-supplier/")
        self.assertEqual(resp.status_code, 400)  # no lines yet

        self.client.post(
            f"/api/purchasing/orders/{order_id}/lines/",
            {"ingredient": self.chicken.id, "quantity": "50", "unit_cost": "8000"},
            format="json",
        )
        resp = self.client.post(f"/api/purchasing/orders/{order_id}/notify-supplier/")
        self.assertEqual(resp.status_code, 200, resp.content)

        log = NotificationLog.objects.get(notification_type=NotificationLog.NotificationType.PURCHASE_ORDER)
        self.assertEqual(log.recipient_phone, "0700999888")

    def test_purchase_orders_are_tenant_scoped(self):
        other_cafe = Cafe.objects.create(name="2Kings")
        other_branch = Branch.objects.create(tenant=other_cafe, name="Ntinda")
        other_manager = User.objects.create_user(
            email="manager@2kings.co", password="pw12345!", role=User.Role.MANAGER, cafe=other_cafe, branch=other_branch
        )

        self.client.login(email="manager@javas.co", password="pw12345!")
        resp = self.client.post("/api/purchasing/orders/", {"supplier": self.supplier.id}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.client.logout()

        self.client.login(email="manager@2kings.co", password="pw12345!")
        resp = self.client.get("/api/purchasing/orders/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 0)
