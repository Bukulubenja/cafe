from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.closing.models import DailyClosing
from apps.complimentary.models import ComplimentaryMeal
from apps.core.context import set_current_branch, set_current_tenant
from apps.expenses.models import Expense
from apps.inventory.models import Ingredient, RecipeItem, StockItem
from apps.menu.models import Category, MenuItem
from apps.payroll.models import PayrollRun, SalaryRecord
from apps.pos.models import Order, OrderItem, Table
from apps.purchasing.models import PurchaseOrder, PurchaseOrderLine, Supplier
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


class RecipeCostAlertTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)

        category = Category.objects.create(name="Lunch")
        # Priced assuming Chicken costs 4000/piece; recipe uses 1 piece, so
        # assumed cost_price is 4000. Stock's actual buying_price will be
        # bumped past that in each test to simulate a market price rise.
        self.pilau = MenuItem.objects.create(
            category=category, name="Chicken Pilau", selling_price=Decimal("15000"), cost_price=Decimal("4000")
        )
        self.chicken = Ingredient.objects.create(name="Chicken", unit=Ingredient.Unit.PIECE)
        RecipeItem.objects.create(menu_item=self.pilau, ingredient=self.chicken, quantity_required=Decimal("1"))

        # No recipe at all -- must be silently skipped, not treated as a
        # 0-cost item that would otherwise never trip the alert.
        self.water = MenuItem.objects.create(
            category=category, name="Bottled Water", selling_price=Decimal("2000"), cost_price=Decimal("800")
        )

        set_current_tenant(None)
        set_current_branch(None)

        self.manager = User.objects.create_user(
            email="manager@javas.co", password="pw12345!", role=User.Role.MANAGER, cafe=self.cafe, branch=self.branch
        )
        self.client = APIClient()
        self.client.login(email="manager@javas.co", password="pw12345!")

    def test_no_alert_when_market_price_has_not_risen(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        StockItem.objects.create(ingredient=self.chicken, buying_price=Decimal("4000"))
        set_current_tenant(None)
        set_current_branch(None)

        resp = self.client.get("/api/reports/dashboard/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["recipe_cost_alerts"], [])

    def test_alert_when_market_price_has_risen_above_assumed_cost(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        StockItem.objects.create(ingredient=self.chicken, buying_price=Decimal("6000"))
        set_current_tenant(None)
        set_current_branch(None)

        resp = self.client.get("/api/reports/dashboard/")
        self.assertEqual(resp.status_code, 200, resp.content)
        alerts = resp.data["recipe_cost_alerts"]
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["menu_item"], "Chicken Pilau")
        self.assertEqual(alerts[0]["assumed_cost"], Decimal("4000.00"))
        self.assertEqual(alerts[0]["actual_cost"], Decimal("6000.00"))
        self.assertEqual(alerts[0]["actual_margin"], Decimal("9000.00"))


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


class BalanceSheetViewTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)

        category = Category.objects.create(name="Lunch")
        item = MenuItem.objects.create(
            category=category, name="Rice", selling_price=Decimal("10000"), cost_price=Decimal("4000")
        )
        table = Table.objects.create(name="T1")
        order = Order.objects.create(table=table)
        OrderItem.objects.create(order=order, menu_item=item, quantity=1)
        order.mark_paid(Order.PaymentMethod.CASH)

        Expense.objects.create(category=Expense.Category.ELECTRICITY, amount=Decimal("2000"))

        chicken = Ingredient.objects.create(name="Chicken", unit=Ingredient.Unit.PIECE)
        StockItem.objects.create(ingredient=chicken, quantity_on_hand=Decimal("10"), buying_price=Decimal("200"))

        self.waiter = User.objects.create_user(
            email="waiter@javas.co", password="pw12345!", role=User.Role.WAITER, cafe=self.cafe, branch=self.branch
        )
        SalaryRecord.objects.create(staff=self.waiter, base_salary=Decimal("100000"), effective_date="2026-01-01")
        today = timezone.localdate()
        PayrollRun.process(self.branch, period_start=today.replace(day=1), period_end=today)

        supplier = Supplier.objects.create(name="Fresh Cuts Ltd")
        po = PurchaseOrder.objects.create(supplier=supplier)
        PurchaseOrderLine.objects.create(purchase_order=po, ingredient=chicken, quantity=Decimal("5"), unit_cost=Decimal("1000"))
        po.receive()  # unpaid -> supplier balance of 5000 becomes a liability

        DailyClosing.close_day(self.branch, cash_counted=Decimal("15000"))

        set_current_tenant(None)
        set_current_branch(None)

        self.manager = User.objects.create_user(
            email="manager@javas.co", password="pw12345!", role=User.Role.MANAGER, cafe=self.cafe, branch=self.branch
        )
        self.client = APIClient()
        self.client.login(email="manager@javas.co", password="pw12345!")

    def test_income_statement(self):
        resp = self.client.get("/api/reports/balance-sheet/")
        self.assertEqual(resp.status_code, 200, resp.content)
        income = resp.data["income"]
        self.assertEqual(income["sales"], Decimal("10000.00"))
        self.assertEqual(income["cogs"], Decimal("4000.00"))
        self.assertEqual(income["gross_profit"], Decimal("6000.00"))
        self.assertEqual(income["total_expenses"], Decimal("2000.00"))
        self.assertEqual(income["purchases"], Decimal("5000.00"))
        self.assertEqual(income["payroll"], Decimal("100000.00"))
        self.assertEqual(income["net_profit"], Decimal("-96000.00"))

    def test_assets_liabilities_equity(self):
        resp = self.client.get("/api/reports/balance-sheet/")
        self.assertEqual(resp.status_code, 200, resp.content)
        # 10 on hand + 5 received via the purchase order = 15, all revalued
        # to the PO's 1000 unit cost (receive() updates buying_price to the
        # latest market price, not just quantity_on_hand)
        self.assertEqual(resp.data["assets"]["inventory_value"], Decimal("15000.00"))
        self.assertEqual(resp.data["assets"]["cash_on_hand"], Decimal("15000.00"))
        self.assertEqual(resp.data["assets"]["total"], Decimal("30000.00"))
        self.assertEqual(resp.data["liabilities"]["accounts_payable"], Decimal("5000.00"))
        self.assertEqual(resp.data["owner_equity"], Decimal("25000.00"))

    def test_waiter_forbidden(self):
        self.client.logout()
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.get("/api/reports/balance-sheet/")
        self.assertEqual(resp.status_code, 403)

    def test_invalid_period_rejected(self):
        resp = self.client.get("/api/reports/balance-sheet/?period_start=2026-08-01&period_end=2026-01-01")
        self.assertEqual(resp.status_code, 400)


class LeaderboardViewTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)

        category = Category.objects.create(name="Lunch")
        item = MenuItem.objects.create(
            category=category, name="Chicken Pilau", selling_price=Decimal("15000"), vat_rate=Decimal("0")
        )
        table = Table.objects.create(name="T1")

        self.top_waiter = User.objects.create_user(
            email="waiter1@javas.co", password="pw12345!", role=User.Role.WAITER, cafe=self.cafe, branch=self.branch
        )
        self.other_waiter = User.objects.create_user(
            email="waiter2@javas.co", password="pw12345!", role=User.Role.WAITER, cafe=self.cafe, branch=self.branch
        )
        self.fast_chef = User.objects.create_user(
            email="chef1@javas.co", password="pw12345!", role=User.Role.CHEF, cafe=self.cafe, branch=self.branch
        )
        self.slow_chef = User.objects.create_user(
            email="chef2@javas.co", password="pw12345!", role=User.Role.CHEF, cafe=self.cafe, branch=self.branch
        )

        # top_waiter: two paid orders (30000 total); other_waiter: one (15000)
        for _ in range(2):
            order = Order.objects.create(table=table, created_by=self.top_waiter)
            OrderItem.objects.create(order=order, menu_item=item, quantity=1)
            order.mark_paid(Order.PaymentMethod.CASH)
        order = Order.objects.create(table=table, created_by=self.other_waiter)
        OrderItem.objects.create(order=order, menu_item=item, quantity=1)
        order.mark_paid(Order.PaymentMethod.CASH)

        # fast_chef cooks in 5 minutes, slow_chef in 20 minutes -- a
        # separate open order so its tickets don't retroactively inflate
        # other_waiter's already-paid order total above
        kitchen_order = Order.objects.create(table=table, created_by=self.other_waiter)
        now = timezone.now()
        fast_ticket = OrderItem.objects.create(order=kitchen_order, menu_item=item, quantity=1)
        fast_ticket.cooked_by = self.fast_chef
        fast_ticket.kitchen_status = OrderItem.KitchenStatus.READY
        fast_ticket.started_cooking_at = now
        fast_ticket.ready_at = now + timezone.timedelta(minutes=5)
        fast_ticket.save()

        slow_ticket = OrderItem.objects.create(order=kitchen_order, menu_item=item, quantity=1)
        slow_ticket.cooked_by = self.slow_chef
        slow_ticket.kitchen_status = OrderItem.KitchenStatus.READY
        slow_ticket.started_cooking_at = now
        slow_ticket.ready_at = now + timezone.timedelta(minutes=20)
        slow_ticket.save()

        set_current_tenant(None)
        set_current_branch(None)

        self.manager = User.objects.create_user(
            email="manager@javas.co", password="pw12345!", role=User.Role.MANAGER, cafe=self.cafe, branch=self.branch
        )
        self.client = APIClient()
        self.client.login(email="manager@javas.co", password="pw12345!")

    def test_best_waiter_ranked_by_revenue(self):
        resp = self.client.get("/api/reports/leaderboards/")
        self.assertEqual(resp.status_code, 200, resp.content)
        top = resp.data["best_waiters"][0]
        self.assertEqual(top["staff"], "waiter1@javas.co")
        self.assertEqual(top["revenue"], Decimal("30000.00"))
        self.assertEqual(top["orders"], 2)

    def test_fastest_chef_ranked_by_average_cook_time(self):
        resp = self.client.get("/api/reports/leaderboards/")
        self.assertEqual(resp.status_code, 200, resp.content)
        chefs = resp.data["fastest_chefs"]
        self.assertEqual(chefs[0]["staff"], "chef1@javas.co")
        self.assertEqual(chefs[0]["avg_minutes"], 5.0)
        self.assertEqual(chefs[1]["staff"], "chef2@javas.co")
        self.assertEqual(chefs[1]["avg_minutes"], 20.0)

    def test_waiter_forbidden(self):
        self.client.logout()
        self.client.login(email="waiter1@javas.co", password="pw12345!")
        resp = self.client.get("/api/reports/leaderboards/")
        self.assertEqual(resp.status_code, 403)

    def test_invalid_window_days_rejected(self):
        resp = self.client.get("/api/reports/leaderboards/?window_days=-5")
        self.assertEqual(resp.status_code, 400)
