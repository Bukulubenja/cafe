from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.core.context import set_current_branch, set_current_tenant
from apps.core.models import AuditLog
from apps.inventory.models import Ingredient, RecipeItem, StockItem
from apps.menu.models import Category, MenuItem
from apps.pos.models import Order, Table
from apps.tenants.models import Branch, Cafe

from .models import Customer, LoyaltyTransaction
from .services import redeem_points


class CustomerComputedFieldTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        self.customer = Customer.objects.create(name="Amina", phone="0700111222")
        self.table = Table.objects.create(name="T1")

    def tearDown(self):
        set_current_tenant(None)
        set_current_branch(None)

    def test_visit_count_and_total_spent_from_paid_orders(self):
        o1 = Order.objects.create(table=self.table, customer=self.customer)
        o1.mark_paid(Order.PaymentMethod.CASH)
        o2 = Order.objects.create(table=self.table, customer=self.customer)
        o2.mark_paid(Order.PaymentMethod.CASH)
        Order.objects.create(table=self.table, customer=self.customer)  # still open, shouldn't count

        self.assertEqual(self.customer.visit_count, 2)
        self.assertEqual(self.customer.total_spent, Decimal("0.00"))  # no items on either order

    def test_loyalty_points_balance_nets_earn_and_redeem(self):
        LoyaltyTransaction.objects.create(
            customer=self.customer, transaction_type=LoyaltyTransaction.Type.EARN, points=10
        )
        LoyaltyTransaction.objects.create(
            customer=self.customer, transaction_type=LoyaltyTransaction.Type.REDEEM, points=3
        )
        self.assertEqual(self.customer.loyalty_points_balance, 7)

    def test_phone_unique_per_cafe(self):
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            Customer.objects.create(name="Someone Else", phone="0700111222")


class LoyaltyEarnTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        self.customer = Customer.objects.create(name="Amina", phone="0700111222")
        category = Category.objects.create(name="Lunch")
        self.pilau = MenuItem.objects.create(category=category, name="Chicken Pilau", selling_price=Decimal("60000"))
        self.table = Table.objects.create(name="T1")

    def tearDown(self):
        set_current_tenant(None)
        set_current_branch(None)

    def test_earns_one_point_per_50000_spent_on_payment(self):
        order = Order.objects.create(table=self.table, customer=self.customer)
        from apps.pos.models import OrderItem

        OrderItem.objects.create(order=order, menu_item=self.pilau, quantity=2)  # 120,000 total
        order.mark_paid(Order.PaymentMethod.CASH)

        self.assertEqual(self.customer.loyalty_points_balance, 2)

    def test_no_customer_is_a_noop(self):
        order = Order.objects.create(table=self.table)  # no customer
        order.mark_paid(Order.PaymentMethod.CASH)
        self.assertEqual(LoyaltyTransaction.objects.count(), 0)

    def test_under_threshold_earns_nothing(self):
        order = Order.objects.create(table=self.table, customer=self.customer)
        from apps.pos.models import OrderItem

        cheap_item = MenuItem.objects.create(category=self.pilau.category, name="Tea", selling_price=Decimal("1000"))
        OrderItem.objects.create(order=order, menu_item=cheap_item, quantity=1)
        order.mark_paid(Order.PaymentMethod.CASH)
        self.assertEqual(self.customer.loyalty_points_balance, 0)


class RedemptionTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        self.customer = Customer.objects.create(name="Amina", phone="0700111222")

        self.juice_ing = Ingredient.objects.create(name="Passion Juice", unit=Ingredient.Unit.MILLILITRE)
        self.stock = StockItem.objects.create(ingredient=self.juice_ing, quantity_on_hand=Decimal("1000"))
        category = Category.objects.create(name="Drinks")
        self.juice = MenuItem.objects.create(
            category=category, name="Juice", selling_price=Decimal("3000"), points_cost=50
        )
        RecipeItem.objects.create(menu_item=self.juice, ingredient=self.juice_ing, quantity_required=Decimal("250"))

        self.not_redeemable = MenuItem.objects.create(category=category, name="Water", selling_price=Decimal("1000"))

        LoyaltyTransaction.objects.create(
            customer=self.customer, transaction_type=LoyaltyTransaction.Type.EARN, points=100
        )

    def tearDown(self):
        set_current_tenant(None)
        set_current_branch(None)

    def test_redeem_deducts_points_and_stock(self):
        redeem_points(self.customer, self.juice, self.branch)
        self.assertEqual(self.customer.loyalty_points_balance, 50)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity_on_hand, Decimal("750"))
        self.assertTrue(AuditLog.unscoped.filter(action="loyalty.redeemed").exists())

    def test_redeem_non_redeemable_item_fails(self):
        with self.assertRaises(ValidationError):
            redeem_points(self.customer, self.not_redeemable, self.branch)

    def test_redeem_with_insufficient_points_fails(self):
        expensive = MenuItem.objects.create(
            category=self.juice.category, name="Burger", selling_price=Decimal("15000"), points_cost=500
        )
        with self.assertRaises(ValidationError):
            redeem_points(self.customer, expensive, self.branch)
        self.assertEqual(self.customer.loyalty_points_balance, 100)  # untouched

    def test_redeem_insufficient_stock_leaves_points_untouched(self):
        thirsty = MenuItem.objects.create(
            category=self.juice.category, name="Big Juice", selling_price=Decimal("3000"), points_cost=10
        )
        RecipeItem.objects.create(menu_item=thirsty, ingredient=self.juice_ing, quantity_required=Decimal("5000"))
        with self.assertRaises(ValidationError):
            redeem_points(self.customer, thirsty, self.branch)
        self.assertEqual(self.customer.loyalty_points_balance, 100)


class CustomerApiTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        self.customer = Customer.objects.create(name="Amina", phone="0700111222")
        category = Category.objects.create(name="Drinks")
        self.juice = MenuItem.objects.create(
            category=category, name="Juice", selling_price=Decimal("3000"), points_cost=50
        )
        self.juice_ing = Ingredient.objects.create(name="Passion Juice", unit=Ingredient.Unit.MILLILITRE)
        StockItem.objects.create(ingredient=self.juice_ing, quantity_on_hand=Decimal("1000"))
        RecipeItem.objects.create(menu_item=self.juice, ingredient=self.juice_ing, quantity_required=Decimal("250"))
        LoyaltyTransaction.objects.create(
            customer=self.customer, transaction_type=LoyaltyTransaction.Type.EARN, points=100
        )
        set_current_tenant(None)
        set_current_branch(None)

        self.waiter = User.objects.create_user(
            email="waiter@javas.co", password="pw12345!", role=User.Role.WAITER, cafe=self.cafe, branch=self.branch
        )
        self.chef = User.objects.create_user(
            email="chef@javas.co", password="pw12345!", role=User.Role.CHEF, cafe=self.cafe, branch=self.branch
        )
        self.client = APIClient()

    def test_waiter_can_create_customer_chef_cannot(self):
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post("/api/customers/customers/", {"name": "Kato", "phone": "0700999888"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)

        self.client.logout()
        self.client.login(email="chef@javas.co", password="pw12345!")
        resp = self.client.post("/api/customers/customers/", {"name": "Kato2", "phone": "0700999889"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_waiter_can_redeem_points(self):
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post(f"/api/customers/customers/{self.customer.id}/redeem/", {"menu_item": self.juice.id})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["points"], 50)

        resp = self.client.get(f"/api/customers/customers/{self.customer.id}/")
        self.assertEqual(resp.data["loyalty_points_balance"], 50)

    def test_customers_are_tenant_scoped(self):
        other_cafe = Cafe.objects.create(name="2Kings")
        other_branch = Branch.objects.create(tenant=other_cafe, name="Ntinda")
        other_waiter = User.objects.create_user(
            email="waiter@2kings.co", password="pw12345!", role=User.Role.WAITER, cafe=other_cafe, branch=other_branch
        )

        self.client.login(email="waiter@2kings.co", password="pw12345!")
        resp = self.client.get("/api/customers/customers/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 0)
