from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.core.context import set_current_branch, set_current_tenant
from apps.menu.models import Category, MenuItem
from apps.tenants.models import Branch, Cafe

from .models import Order, OrderItem, Table


class OrderModelTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        self.category = Category.objects.create(name="Lunch")
        self.kitchen_item = MenuItem.objects.create(
            category=self.category,
            name="Chicken Pilau",
            selling_price=Decimal("15000"),
            vat_rate=Decimal("18.00"),
        )
        self.drink_item = MenuItem.objects.create(
            category=self.category, name="Bottled Water", selling_price=Decimal("2000"), requires_kitchen=False
        )
        self.table = Table.objects.create(name="T1")

    def tearDown(self):
        set_current_tenant(None)
        set_current_branch(None)

    def _make_order(self):
        return Order.objects.create(table=self.table)

    def test_kitchen_item_snapshots_price_and_starts_pending(self):
        order = self._make_order()
        item = OrderItem.objects.create(order=order, menu_item=self.kitchen_item, quantity=2)
        self.assertEqual(item.unit_price, Decimal("15000"))
        self.assertEqual(item.vat_rate, Decimal("18.00"))
        self.assertTrue(item.requires_kitchen)
        self.assertEqual(item.kitchen_status, OrderItem.KitchenStatus.PENDING)

    def test_non_kitchen_item_is_auto_served(self):
        order = self._make_order()
        item = OrderItem.objects.create(order=order, menu_item=self.drink_item, quantity=1)
        self.assertFalse(item.requires_kitchen)
        self.assertEqual(item.kitchen_status, OrderItem.KitchenStatus.SERVED)
        self.assertIsNotNone(item.served_at)

    def test_order_totals(self):
        order = self._make_order()
        OrderItem.objects.create(order=order, menu_item=self.kitchen_item, quantity=2)  # 30000 + 18% vat
        OrderItem.objects.create(order=order, menu_item=self.drink_item, quantity=1)  # 2000, no vat
        self.assertEqual(order.subtotal, Decimal("32000.00"))
        self.assertEqual(order.vat_total, Decimal("5400.00"))
        self.assertEqual(order.total, Decimal("37400.00"))

    def test_cancelled_items_excluded_from_totals(self):
        order = self._make_order()
        item = OrderItem.objects.create(order=order, menu_item=self.kitchen_item, quantity=1)
        item.cancel()
        self.assertEqual(order.subtotal, Decimal("0.00"))

    def test_kitchen_transition_happy_path(self):
        order = self._make_order()
        item = OrderItem.objects.create(order=order, menu_item=self.kitchen_item, quantity=1)
        item.mark_cooking()
        self.assertEqual(item.kitchen_status, OrderItem.KitchenStatus.COOKING)
        self.assertIsNotNone(item.started_cooking_at)
        item.mark_ready()
        self.assertEqual(item.kitchen_status, OrderItem.KitchenStatus.READY)
        item.mark_served()
        self.assertEqual(item.kitchen_status, OrderItem.KitchenStatus.SERVED)

    def test_kitchen_transition_rejects_skipping_steps(self):
        order = self._make_order()
        item = OrderItem.objects.create(order=order, menu_item=self.kitchen_item, quantity=1)
        with self.assertRaises(ValidationError):
            item.mark_ready()

    def test_dine_in_requires_table(self):
        order = Order(order_type=Order.OrderType.DINE_IN)
        with self.assertRaises(ValidationError):
            order.full_clean(exclude=["tenant", "branch", "created_by"])

    def test_mark_paid_frees_table_and_logs_audit(self):
        self.table.status = Table.Status.OCCUPIED
        self.table.save(update_fields=["status"])
        order = self._make_order()
        OrderItem.objects.create(order=order, menu_item=self.kitchen_item, quantity=1)

        order.mark_paid(Order.PaymentMethod.CASH)

        order.refresh_from_db()
        self.table.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.payment_method, Order.PaymentMethod.CASH)
        self.assertIsNotNone(order.closed_at)
        self.assertEqual(self.table.status, Table.Status.AVAILABLE)

    def test_cannot_pay_twice(self):
        order = self._make_order()
        order.mark_paid(Order.PaymentMethod.CASH)
        with self.assertRaises(ValidationError):
            order.mark_paid(Order.PaymentMethod.CASH)


class PosApiTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")

        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        self.category = Category.objects.create(name="Lunch")
        self.menu_item = MenuItem.objects.create(
            category=self.category, name="Chicken Pilau", selling_price=Decimal("15000")
        )
        self.table = Table.objects.create(name="T1")
        set_current_tenant(None)
        set_current_branch(None)

        self.waiter = User.objects.create_user(
            email="waiter@javas.co", password="pw12345!", role=User.Role.WAITER, cafe=self.cafe, branch=self.branch
        )
        self.chef = User.objects.create_user(
            email="chef@javas.co", password="pw12345!", role=User.Role.CHEF, cafe=self.cafe, branch=self.branch
        )
        self.cashier = User.objects.create_user(
            email="cashier@javas.co", password="pw12345!", role=User.Role.CASHIER, cafe=self.cafe, branch=self.branch
        )
        self.client = APIClient()

    def test_waiter_can_create_order_and_add_item(self):
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post("/api/pos/orders/", {"table": self.table.id, "order_type": "dine_in"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        order_id = resp.data["id"]

        resp = self.client.post(
            f"/api/pos/orders/{order_id}/items/", {"menu_item": self.menu_item.id, "quantity": 2}, format="json"
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["quantity"], 2)

    def test_cashier_can_take_payment_but_not_create_order(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        order = Order.objects.create(table=self.table, created_by=self.waiter)
        set_current_tenant(None)
        set_current_branch(None)

        self.client.login(email="cashier@javas.co", password="pw12345!")
        resp = self.client.post("/api/pos/orders/", {"table": self.table.id, "order_type": "dine_in"}, format="json")
        self.assertEqual(resp.status_code, 403)

        resp = self.client.post(f"/api/pos/orders/{order.id}/pay/", {"payment_method": "cash"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["status"], "paid")

    def test_chef_cannot_take_payment(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        order = Order.objects.create(table=self.table, created_by=self.waiter)
        set_current_tenant(None)
        set_current_branch(None)

        self.client.login(email="chef@javas.co", password="pw12345!")
        resp = self.client.post(f"/api/pos/orders/{order.id}/pay/", {"payment_method": "cash"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_chef_cannot_create_order(self):
        self.client.login(email="chef@javas.co", password="pw12345!")
        resp = self.client.post("/api/pos/orders/", {"table": self.table.id, "order_type": "dine_in"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_chef_can_drive_kitchen_queue_waiter_cannot(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        order = Order.objects.create(table=self.table, created_by=self.waiter)
        item = OrderItem.objects.create(order=order, menu_item=self.menu_item, quantity=1)
        set_current_tenant(None)
        set_current_branch(None)

        self.client.login(email="chef@javas.co", password="pw12345!")
        resp = self.client.get("/api/pos/kitchen/queue/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertNotIn("unit_price", resp.data[0])

        resp = self.client.post(f"/api/pos/kitchen/queue/{item.id}/start-cooking/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["kitchen_status"], "cooking")

        self.client.logout()
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post(f"/api/pos/kitchen/queue/{item.id}/ready/")
        self.assertEqual(resp.status_code, 403)

    def test_orders_are_tenant_scoped_across_cafes(self):
        other_cafe = Cafe.objects.create(name="2Kings")
        other_branch = Branch.objects.create(tenant=other_cafe, name="Ntinda")
        other_waiter = User.objects.create_user(
            email="waiter@2kings.co", password="pw12345!", role=User.Role.WAITER, cafe=other_cafe, branch=other_branch
        )

        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post("/api/pos/orders/", {"table": self.table.id, "order_type": "dine_in"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.client.logout()

        self.client.login(email="waiter@2kings.co", password="pw12345!")
        resp = self.client.get("/api/pos/orders/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 0)
