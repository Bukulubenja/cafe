import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.core.context import set_current_branch, set_current_tenant
from apps.inventory.models import Ingredient, RecipeItem, StockItem
from apps.menu.models import Category, MenuItem
from apps.tenants.models import Branch, Cafe

from .models import Order, OrderItem, Refund, Table


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

    def test_split_off_moves_selected_items_to_a_new_order(self):
        order = self._make_order()
        pilau = OrderItem.objects.create(order=order, menu_item=self.kitchen_item, quantity=1)
        water = OrderItem.objects.create(order=order, menu_item=self.drink_item, quantity=1)

        new_order = order.split_off([water.id])
        water.refresh_from_db()

        self.assertEqual(new_order.table, order.table)
        self.assertEqual(list(order.active_items), [pilau])
        self.assertEqual(list(new_order.active_items), [water])
        self.assertEqual(order.total, Decimal("17700.00"))  # 15000 + 18% vat
        self.assertEqual(new_order.total, Decimal("2000.00"))

    def test_split_off_rejects_moving_every_item(self):
        order = self._make_order()
        item = OrderItem.objects.create(order=order, menu_item=self.kitchen_item, quantity=1)
        with self.assertRaises(ValidationError):
            order.split_off([item.id])

    def test_split_off_rejects_empty_selection(self):
        order = self._make_order()
        OrderItem.objects.create(order=order, menu_item=self.kitchen_item, quantity=1)
        with self.assertRaises(ValidationError):
            order.split_off([])

    def test_cannot_split_a_paid_order(self):
        order = self._make_order()
        item1 = OrderItem.objects.create(order=order, menu_item=self.kitchen_item, quantity=1)
        OrderItem.objects.create(order=order, menu_item=self.drink_item, quantity=1)
        order.mark_paid(Order.PaymentMethod.CASH)
        with self.assertRaises(ValidationError):
            order.split_off([item1.id])

    def test_transfer_table_moves_order_and_swaps_table_status(self):
        table2 = Table.objects.create(name="T2")
        self.table.status = Table.Status.OCCUPIED
        self.table.save(update_fields=["status"])
        order = self._make_order()

        order.transfer_table(table2)

        order.refresh_from_db()
        self.table.refresh_from_db()
        table2.refresh_from_db()
        self.assertEqual(order.table, table2)
        self.assertEqual(self.table.status, Table.Status.AVAILABLE)
        self.assertEqual(table2.status, Table.Status.OCCUPIED)

    def test_cannot_transfer_to_a_table_with_an_open_order(self):
        table2 = Table.objects.create(name="T2")
        Order.objects.create(table=table2)
        order = self._make_order()
        with self.assertRaises(ValidationError):
            order.transfer_table(table2)

    def test_cannot_transfer_takeaway_order(self):
        order = Order.objects.create(order_type=Order.OrderType.TAKEAWAY)
        table2 = Table.objects.create(name="T2")
        with self.assertRaises(ValidationError):
            order.transfer_table(table2)

    def test_cannot_transfer_paid_order(self):
        table2 = Table.objects.create(name="T2")
        order = self._make_order()
        OrderItem.objects.create(order=order, menu_item=self.drink_item, quantity=1)
        order.mark_paid(Order.PaymentMethod.CASH)
        with self.assertRaises(ValidationError):
            order.transfer_table(table2)

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

    def test_mark_paid_sends_whatsapp_receipt_to_linked_customer(self):
        from apps.customers.models import Customer
        from apps.notifications.models import NotificationLog

        customer = Customer.objects.create(name="Amina", phone="0700111222")
        order = Order.objects.create(table=self.table, customer=customer)
        OrderItem.objects.create(order=order, menu_item=self.drink_item, quantity=1)

        order.mark_paid(Order.PaymentMethod.CASH)

        log = NotificationLog.objects.get(notification_type=NotificationLog.NotificationType.RECEIPT)
        self.assertEqual(log.recipient_phone, "0700111222")
        self.assertEqual(log.status, NotificationLog.Status.SENT)


class StockDeductionIntegrationTests(TestCase):
    """Recipe-based stock deduction, wired into the kitchen ticket workflow."""

    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)

        self.category = Category.objects.create(name="Lunch")
        self.kitchen_item = MenuItem.objects.create(
            category=self.category, name="Chicken Pilau", selling_price=Decimal("15000")
        )
        self.drink_item = MenuItem.objects.create(
            category=self.category, name="Bottled Water", selling_price=Decimal("2000"), requires_kitchen=False
        )

        self.chicken = Ingredient.objects.create(name="Chicken", unit=Ingredient.Unit.PIECE)
        self.chicken_stock = StockItem.objects.create(ingredient=self.chicken, quantity_on_hand=Decimal("5"))
        RecipeItem.objects.create(menu_item=self.kitchen_item, ingredient=self.chicken, quantity_required=Decimal("1"))

        self.bottle = Ingredient.objects.create(name="Bottled Water 500ml", unit=Ingredient.Unit.PIECE)
        self.bottle_stock = StockItem.objects.create(ingredient=self.bottle, quantity_on_hand=Decimal("3"))
        RecipeItem.objects.create(menu_item=self.drink_item, ingredient=self.bottle, quantity_required=Decimal("1"))

        self.table = Table.objects.create(name="T1")
        self.order = Order.objects.create(table=self.table)

    def tearDown(self):
        set_current_tenant(None)
        set_current_branch(None)

    def test_non_kitchen_item_deducts_stock_immediately(self):
        OrderItem.objects.create(order=self.order, menu_item=self.drink_item, quantity=2)
        self.bottle_stock.refresh_from_db()
        self.assertEqual(self.bottle_stock.quantity_on_hand, Decimal("1"))

    def test_kitchen_item_does_not_deduct_until_cooking(self):
        item = OrderItem.objects.create(order=self.order, menu_item=self.kitchen_item, quantity=2)
        self.chicken_stock.refresh_from_db()
        self.assertEqual(self.chicken_stock.quantity_on_hand, Decimal("5"))  # untouched

        item.mark_cooking()
        self.chicken_stock.refresh_from_db()
        self.assertEqual(self.chicken_stock.quantity_on_hand, Decimal("3"))  # 5 - 2

    def test_mark_cooking_fails_on_insufficient_stock_and_stays_pending(self):
        item = OrderItem.objects.create(order=self.order, menu_item=self.kitchen_item, quantity=10)
        with self.assertRaises(ValidationError):
            item.mark_cooking()

        item.refresh_from_db()
        self.chicken_stock.refresh_from_db()
        self.assertEqual(item.kitchen_status, OrderItem.KitchenStatus.PENDING)
        self.assertEqual(self.chicken_stock.quantity_on_hand, Decimal("5"))

    def test_non_kitchen_item_creation_rolls_back_on_insufficient_stock(self):
        with self.assertRaises(ValidationError):
            OrderItem.objects.create(order=self.order, menu_item=self.drink_item, quantity=10)

        self.bottle_stock.refresh_from_db()
        self.assertEqual(self.bottle_stock.quantity_on_hand, Decimal("3"))
        self.assertEqual(self.order.items.count(), 0)


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

    def test_cannot_add_item_that_is_out_of_stock(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        chicken = Ingredient.objects.create(name="Chicken", unit=Ingredient.Unit.PIECE)
        StockItem.objects.create(ingredient=chicken, quantity_on_hand=Decimal("0"))
        RecipeItem.objects.create(menu_item=self.menu_item, ingredient=chicken, quantity_required=Decimal("1"))
        set_current_tenant(None)
        set_current_branch(None)

        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post("/api/pos/orders/", {"table": self.table.id, "order_type": "dine_in"}, format="json")
        order_id = resp.data["id"]

        resp = self.client.post(
            f"/api/pos/orders/{order_id}/items/", {"menu_item": self.menu_item.id, "quantity": 1}, format="json"
        )
        self.assertEqual(resp.status_code, 400)

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

    def test_waiter_can_split_bill_cashier_cannot(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        order = Order.objects.create(table=self.table, created_by=self.waiter)
        item1 = OrderItem.objects.create(order=order, menu_item=self.menu_item, quantity=1)
        OrderItem.objects.create(order=order, menu_item=self.menu_item, quantity=1)
        set_current_tenant(None)
        set_current_branch(None)

        self.client.login(email="cashier@javas.co", password="pw12345!")
        resp = self.client.post(f"/api/pos/orders/{order.id}/split/", {"item_ids": [item1.id]}, format="json")
        self.assertEqual(resp.status_code, 403)

        self.client.logout()
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post(f"/api/pos/orders/{order.id}/split/", {"item_ids": [item1.id]}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["table"], self.table.id)
        self.assertEqual(len(resp.data["items"]), 1)

    def test_waiter_can_transfer_table_cashier_cannot(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        table2 = Table.objects.create(name="T2")
        order = Order.objects.create(table=self.table, created_by=self.waiter)
        set_current_tenant(None)
        set_current_branch(None)

        self.client.login(email="cashier@javas.co", password="pw12345!")
        resp = self.client.post(f"/api/pos/orders/{order.id}/transfer-table/", {"table": table2.id}, format="json")
        self.assertEqual(resp.status_code, 403)

        self.client.logout()
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post(f"/api/pos/orders/{order.id}/transfer-table/", {"table": table2.id}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["table"], table2.id)

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


class RefundApiTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")

        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        category = Category.objects.create(name="Lunch")
        self.menu_item = MenuItem.objects.create(
            category=category, name="Chicken Pilau", selling_price=Decimal("15000")
        )
        table = Table.objects.create(name="T1")
        self.paid_order = Order.objects.create(table=table)
        OrderItem.objects.create(order=self.paid_order, menu_item=self.menu_item, quantity=1)
        self.paid_order.mark_paid(Order.PaymentMethod.CASH)

        self.open_order = Order.objects.create(order_type=Order.OrderType.TAKEAWAY)
        set_current_tenant(None)
        set_current_branch(None)

        self.waiter = User.objects.create_user(
            email="waiter@javas.co", password="pw12345!", role=User.Role.WAITER, cafe=self.cafe, branch=self.branch
        )
        self.manager = User.objects.create_user(
            email="manager@javas.co", password="pw12345!", role=User.Role.MANAGER, cafe=self.cafe, branch=self.branch
        )
        self.chef = User.objects.create_user(
            email="chef@javas.co", password="pw12345!", role=User.Role.CHEF, cafe=self.cafe, branch=self.branch
        )
        self.client = APIClient()

    def test_waiter_can_request_refund_on_paid_order(self):
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post(
            "/api/pos/refunds/",
            {"order": self.paid_order.id, "amount": "15000.00", "reason": "quality_issue"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["status"], "pending")
        self.assertEqual(resp.data["requested_by_email"], "waiter@javas.co")

    def test_cannot_request_refund_on_open_order(self):
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post(
            "/api/pos/refunds/",
            {"order": self.open_order.id, "amount": "1000.00", "reason": "other"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_cannot_refund_more_than_order_total(self):
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post(
            "/api/pos/refunds/",
            {"order": self.paid_order.id, "amount": "99999.00", "reason": "other"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_chef_cannot_request_refund(self):
        self.client.login(email="chef@javas.co", password="pw12345!")
        resp = self.client.post(
            "/api/pos/refunds/",
            {"order": self.paid_order.id, "amount": "1000.00", "reason": "other"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_manager_approves_waiter_cannot(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        refund = Refund.objects.create(order=self.paid_order, amount=Decimal("15000.00"), reason=Refund.Reason.OTHER)
        set_current_tenant(None)
        set_current_branch(None)

        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post(f"/api/pos/refunds/{refund.id}/approve/")
        self.assertEqual(resp.status_code, 403)

        self.client.logout()
        self.client.login(email="manager@javas.co", password="pw12345!")
        resp = self.client.post(f"/api/pos/refunds/{refund.id}/approve/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["status"], "approved")

    def test_second_refund_capped_by_remaining_balance(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        first = Refund.objects.create(order=self.paid_order, amount=Decimal("10000.00"), reason=Refund.Reason.OTHER)
        first.approve(self.manager)
        set_current_tenant(None)
        set_current_branch(None)

        self.client.login(email="waiter@javas.co", password="pw12345!")
        # order total is 15000; 10000 already approved, so only 5000 remains
        resp = self.client.post(
            "/api/pos/refunds/",
            {"order": self.paid_order.id, "amount": "5001.00", "reason": "other"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

        resp = self.client.post(
            "/api/pos/refunds/",
            {"order": self.paid_order.id, "amount": "5000.00", "reason": "other"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)


class OfflineSyncIdempotencyTests(TestCase):
    """Offline-first: a POS terminal generates a client_id before ever
    reaching the server, so a retried create (after reconnecting, unsure if
    the first attempt landed) can't double-book a sale.
    """

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
        self.client = APIClient()
        self.client.login(email="waiter@javas.co", password="pw12345!")

    def test_retried_order_create_returns_existing_order_not_a_duplicate(self):
        client_id = str(uuid.uuid4())
        payload = {"table": self.table.id, "order_type": "dine_in", "client_id": client_id}

        first = self.client.post("/api/pos/orders/", payload, format="json")
        self.assertEqual(first.status_code, 201, first.content)

        second = self.client.post("/api/pos/orders/", payload, format="json")
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(second.data["id"], first.data["id"])
        self.assertEqual(Order.objects.count(), 1)

    def test_without_client_id_retries_create_duplicates(self):
        payload = {"table": self.table.id, "order_type": "dine_in"}
        self.client.post("/api/pos/orders/", payload, format="json")
        self.client.post("/api/pos/orders/", payload, format="json")
        self.assertEqual(Order.objects.count(), 2)

    def test_malformed_client_id_rejected(self):
        resp = self.client.post(
            "/api/pos/orders/",
            {"table": self.table.id, "order_type": "dine_in", "client_id": "not-a-uuid"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_retried_add_item_returns_existing_item_not_a_duplicate(self):
        order_resp = self.client.post(
            "/api/pos/orders/", {"table": self.table.id, "order_type": "dine_in"}, format="json"
        )
        order_id = order_resp.data["id"]
        client_id = str(uuid.uuid4())
        payload = {"menu_item": self.menu_item.id, "quantity": 2, "client_id": client_id}

        first = self.client.post(f"/api/pos/orders/{order_id}/items/", payload, format="json")
        self.assertEqual(first.status_code, 201, first.content)

        second = self.client.post(f"/api/pos/orders/{order_id}/items/", payload, format="json")
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(second.data["id"], first.data["id"])
        self.assertEqual(OrderItem.objects.filter(order_id=order_id).count(), 1)

    def test_reusing_item_client_id_on_a_different_order_is_rejected(self):
        client_id = str(uuid.uuid4())
        order1 = self.client.post(
            "/api/pos/orders/", {"table": self.table.id, "order_type": "dine_in"}, format="json"
        ).data
        table2 = self._make_second_table()
        order2 = self.client.post(
            "/api/pos/orders/", {"table": table2.id, "order_type": "dine_in"}, format="json"
        ).data

        payload = {"menu_item": self.menu_item.id, "quantity": 1, "client_id": client_id}
        first = self.client.post(f"/api/pos/orders/{order1['id']}/items/", payload, format="json")
        self.assertEqual(first.status_code, 201, first.content)

        conflict = self.client.post(f"/api/pos/orders/{order2['id']}/items/", payload, format="json")
        self.assertEqual(conflict.status_code, 400)

    def _make_second_table(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        table = Table.objects.create(name="T2")
        set_current_tenant(None)
        set_current_branch(None)
        return table

    def test_same_literal_uuid_isolated_across_cafes(self):
        other_cafe = Cafe.objects.create(name="2Kings")
        other_branch = Branch.objects.create(tenant=other_cafe, name="Ntinda")
        other_waiter = User.objects.create_user(
            email="waiter@2kings.co", password="pw12345!", role=User.Role.WAITER, cafe=other_cafe, branch=other_branch
        )
        set_current_tenant(other_cafe)
        set_current_branch(other_branch)
        other_table = Table.objects.create(name="T1")
        set_current_tenant(None)
        set_current_branch(None)

        shared_client_id = str(uuid.uuid4())

        resp = self.client.post(
            "/api/pos/orders/",
            {"table": self.table.id, "order_type": "dine_in", "client_id": shared_client_id},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)

        self.client.logout()
        self.client.login(email="waiter@2kings.co", password="pw12345!")
        resp2 = self.client.post(
            "/api/pos/orders/",
            {"table": other_table.id, "order_type": "dine_in", "client_id": shared_client_id},
            format="json",
        )
        self.assertEqual(resp2.status_code, 201, resp2.content)  # not treated as a duplicate of the other cafe's order
        self.assertEqual(Order.unscoped.filter(client_id=shared_client_id).count(), 2)
