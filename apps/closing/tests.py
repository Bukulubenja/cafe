from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.core.context import set_current_branch, set_current_tenant
from apps.core.models import AuditLog
from apps.menu.models import Category, MenuItem
from apps.pos.models import Order, OrderItem, Table
from apps.tenants.models import Branch, Cafe

from .models import DailyClosing


class DailyClosingTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)

        category = Category.objects.create(name="Lunch")
        self.item = MenuItem.objects.create(category=category, name="Rice", selling_price=Decimal("10000"))
        self.table = Table.objects.create(name="T1")
        self.manager = User.objects.create_user(
            email="manager@javas.co", password="pw12345!", role=User.Role.MANAGER, cafe=self.cafe, branch=self.branch
        )

    def tearDown(self):
        set_current_tenant(None)
        set_current_branch(None)

    def _paid_order(self, payment_method):
        order = Order.objects.create(table=self.table)
        OrderItem.objects.create(order=order, menu_item=self.item, quantity=1)
        order.mark_paid(payment_method)
        return order

    def test_cash_expected_sums_only_paid_cash_orders_for_the_day(self):
        self._paid_order(Order.PaymentMethod.CASH)
        self._paid_order(Order.PaymentMethod.CASH)
        self._paid_order(Order.PaymentMethod.MOBILE_MONEY)  # excluded
        open_order = Order.objects.create(table=self.table)
        OrderItem.objects.create(order=open_order, menu_item=self.item, quantity=1)  # still open, excluded

        closing = DailyClosing.close_day(self.branch, cash_counted=Decimal("20000"), actor=self.manager)

        self.assertEqual(closing.cash_expected, Decimal("20000.00"))
        self.assertEqual(closing.difference, Decimal("0.00"))
        self.assertTrue(AuditLog.unscoped.filter(action="daily_closing.closed").exists())

    def test_difference_reflects_shortfall(self):
        self._paid_order(Order.PaymentMethod.CASH)
        closing = DailyClosing.close_day(self.branch, cash_counted=Decimal("8000"), actor=self.manager)
        self.assertEqual(closing.cash_expected, Decimal("10000.00"))
        self.assertEqual(closing.difference, Decimal("-2000.00"))

    def test_cannot_close_same_branch_and_date_twice(self):
        DailyClosing.close_day(self.branch, cash_counted=Decimal("0"), actor=self.manager)
        with self.assertRaises(ValidationError):
            DailyClosing.close_day(self.branch, cash_counted=Decimal("0"), actor=self.manager)

    def test_other_branch_can_close_same_date_independently(self):
        other_branch = Branch.objects.create(tenant=self.cafe, name="Ntinda")
        DailyClosing.close_day(self.branch, cash_counted=Decimal("0"), actor=self.manager)
        DailyClosing.close_day(other_branch, cash_counted=Decimal("0"), actor=self.manager)  # should not raise


class DailyClosingApiTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        self.manager = User.objects.create_user(
            email="manager@javas.co", password="pw12345!", role=User.Role.MANAGER, cafe=self.cafe, branch=self.branch
        )
        self.waiter = User.objects.create_user(
            email="waiter@javas.co", password="pw12345!", role=User.Role.WAITER, cafe=self.cafe, branch=self.branch
        )
        self.client = APIClient()

    def test_manager_can_close_day_waiter_cannot(self):
        self.client.login(email="manager@javas.co", password="pw12345!")
        resp = self.client.post("/api/closing/closings/", {"cash_counted": "0"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["cash_expected"], "0.00")

        self.client.logout()
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post("/api/closing/closings/", {"cash_counted": "0"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_double_close_returns_400(self):
        self.client.login(email="manager@javas.co", password="pw12345!")
        resp = self.client.post("/api/closing/closings/", {"cash_counted": "0"}, format="json")
        self.assertEqual(resp.status_code, 201)
        resp = self.client.post("/api/closing/closings/", {"cash_counted": "0"}, format="json")
        self.assertEqual(resp.status_code, 400)
