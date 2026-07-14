from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.complimentary.models import ComplimentaryMeal
from apps.core.context import set_current_branch, set_current_tenant
from apps.expenses.models import Expense
from apps.inventory.models import Ingredient, StockItem
from apps.menu.models import Category, MenuItem
from apps.pos.models import Order, OrderItem, Table
from apps.tenants.models import Branch, Cafe
from apps.wastage.models import WastageRecord


class DashboardViewTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)

        category = Category.objects.create(name="Lunch")
        self.item = MenuItem.objects.create(
            category=category, name="Chicken Pilau", selling_price=Decimal("15000"), cost_price=Decimal("6000")
        )
        self.table = Table.objects.create(name="T1")

        order = Order.objects.create(table=self.table)
        OrderItem.objects.create(order=order, menu_item=self.item, quantity=2)
        order.mark_paid(Order.PaymentMethod.CASH)

        Expense.objects.create(category=Expense.Category.ELECTRICITY, amount=Decimal("5000"))

        chicken = Ingredient.objects.create(name="Chicken", unit=Ingredient.Unit.PIECE)
        StockItem.objects.create(ingredient=chicken, quantity_on_hand=Decimal("2"), minimum_quantity=Decimal("5"))

        set_current_tenant(None)
        set_current_branch(None)

        self.manager = User.objects.create_user(
            email="manager@javas.co", password="pw12345!", role=User.Role.MANAGER, cafe=self.cafe, branch=self.branch
        )
        self.waiter = User.objects.create_user(
            email="waiter@javas.co", password="pw12345!", role=User.Role.WAITER, cafe=self.cafe, branch=self.branch
        )
        self.client = APIClient()

    def test_dashboard_totals(self):
        self.client.login(email="manager@javas.co", password="pw12345!")
        resp = self.client.get("/api/reports/dashboard/")
        self.assertEqual(resp.status_code, 200, resp.content)

        self.assertEqual(resp.data["sales_today"], Decimal("30000.00"))
        self.assertEqual(resp.data["orders_today"], 1)
        self.assertEqual(resp.data["expenses_today"], Decimal("5000.00"))
        # profit = 30000 sales - (6000*2) cogs - 5000 expenses = 13000
        self.assertEqual(resp.data["profit_today"], Decimal("13000.00"))
        self.assertEqual(len(resp.data["low_stock_alerts"]), 1)
        self.assertEqual(resp.data["low_stock_alerts"][0]["ingredient"], "Chicken")
        self.assertEqual(resp.data["top_selling_items_today"][0]["menu_item"], "Chicken Pilau")

    def test_waiter_forbidden(self):
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.get("/api/reports/dashboard/")
        self.assertEqual(resp.status_code, 403)

    def test_dashboard_scoped_to_branch(self):
        other_branch = Branch.objects.create(tenant=self.cafe, name="Ntinda")
        other_manager = User.objects.create_user(
            email="manager2@javas.co", password="pw12345!", role=User.Role.MANAGER, cafe=self.cafe, branch=other_branch
        )
        self.client.login(email="manager2@javas.co", password="pw12345!")
        resp = self.client.get("/api/reports/dashboard/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["sales_today"], Decimal("0.00"))
        self.assertEqual(resp.data["orders_today"], 0)


class SalesAndProfitReportTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)

        category = Category.objects.create(name="Lunch")
        self.item = MenuItem.objects.create(
            category=category, name="Rice", selling_price=Decimal("10000"), cost_price=Decimal("4000")
        )
        self.table = Table.objects.create(name="T1")
        order = Order.objects.create(table=self.table)
        OrderItem.objects.create(order=order, menu_item=self.item, quantity=1)
        order.mark_paid(Order.PaymentMethod.CASH)

        set_current_tenant(None)
        set_current_branch(None)

        self.manager = User.objects.create_user(
            email="manager@javas.co", password="pw12345!", role=User.Role.MANAGER, cafe=self.cafe, branch=self.branch
        )
        self.client = APIClient()
        self.client.login(email="manager@javas.co", password="pw12345!")

    def test_sales_report_daily(self):
        resp = self.client.get("/api/reports/sales/?period=daily")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["results"][0]["sales"], Decimal("10000.00"))
        self.assertEqual(resp.data["results"][0]["orders"], 1)

    def test_profit_report_daily(self):
        resp = self.client.get("/api/reports/profit/?period=daily")
        self.assertEqual(resp.status_code, 200, resp.content)
        result = resp.data["results"][0]
        self.assertEqual(result["revenue"], Decimal("10000.00"))
        self.assertEqual(result["cogs"], Decimal("4000.00"))
        self.assertEqual(result["net_profit"], Decimal("6000.00"))

    def test_invalid_period_rejected(self):
        resp = self.client.get("/api/reports/sales/?period=yearly")
        self.assertEqual(resp.status_code, 400)


class LossDetectionTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)

        category = Category.objects.create(name="Drinks")
        self.tea = MenuItem.objects.create(
            category=category, name="Tea", selling_price=Decimal("2000"), cost_price=Decimal("500")
        )
        self.waiter = User.objects.create_user(
            email="waiter@javas.co", password="pw12345!", role=User.Role.WAITER, cafe=self.cafe, branch=self.branch
        )
        self.manager = User.objects.create_user(
            email="manager@javas.co", password="pw12345!", role=User.Role.MANAGER, cafe=self.cafe, branch=self.branch
        )
        self.chicken = Ingredient.objects.create(name="Chicken", unit=Ingredient.Unit.PIECE)
        StockItem.objects.create(ingredient=self.chicken, quantity_on_hand=Decimal("100"))

        # 12 approved comp meals for the same waiter -> should trip the flag (threshold 10)
        for _ in range(12):
            meal = ComplimentaryMeal.objects.create(
                staff=self.waiter, menu_item=self.tea, quantity=1, reason=ComplimentaryMeal.Reason.WAITER_BREAKFAST,
                requested_by=self.waiter,
            )
            meal.approve(self.manager)

        # 6 cancelled orders by the same waiter -> should trip the flag (threshold 5)
        for _ in range(6):
            order = Order.objects.create(created_by=self.waiter, order_type=Order.OrderType.TAKEAWAY)
            order.cancel(self.waiter)

        # large wastage of chicken -> should trip the flag (threshold 10 units)
        WastageRecord.objects.create(
            ingredient=self.chicken, quantity=Decimal("15"), reason=WastageRecord.Reason.SPOILT,
        )

        set_current_tenant(None)
        set_current_branch(None)
        self.client = APIClient()
        self.client.login(email="manager@javas.co", password="pw12345!")

    def test_flags_excessive_complimentary_meals(self):
        resp = self.client.get("/api/reports/loss-detection/")
        self.assertEqual(resp.status_code, 200, resp.content)
        flagged = {f["staff"] for f in resp.data["excessive_complimentary_by_staff"]}
        self.assertIn("waiter@javas.co", flagged)

    def test_flags_excessive_cancellations(self):
        resp = self.client.get("/api/reports/loss-detection/")
        flagged = {f["staff"] for f in resp.data["excessive_cancellations_by_staff"]}
        self.assertIn("waiter@javas.co", flagged)

    def test_flags_excessive_wastage(self):
        resp = self.client.get("/api/reports/loss-detection/")
        flagged = {f["ingredient"] for f in resp.data["excessive_wastage_by_ingredient"]}
        self.assertIn("Chicken", flagged)
