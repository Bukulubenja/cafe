from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.core.context import set_current_branch, set_current_tenant
from apps.tenants.models import Branch, Cafe

from .models import Expense


class ExpenseScopingTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        self.other_branch = Branch.objects.create(tenant=self.cafe, name="Ntinda")

    def test_expense_scoped_to_branch(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        Expense.objects.create(category=Expense.Category.RENT, amount=Decimal("500000"))

        set_current_branch(self.other_branch)
        Expense.objects.create(category=Expense.Category.FUEL, amount=Decimal("100000"))

        set_current_branch(self.branch)
        categories = list(Expense.objects.values_list("category", flat=True))
        self.assertEqual(categories, ["rent"])

        set_current_tenant(None)
        set_current_branch(None)


class ExpenseApiTests(TestCase):
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

    def test_manager_can_record_expense_waiter_cannot(self):
        self.client.login(email="manager@javas.co", password="pw12345!")
        resp = self.client.post(
            "/api/expenses/expenses/", {"category": "electricity", "amount": "80000"}, format="json"
        )
        self.assertEqual(resp.status_code, 201, resp.content)

        self.client.logout()
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post(
            "/api/expenses/expenses/", {"category": "electricity", "amount": "10000"}, format="json"
        )
        self.assertEqual(resp.status_code, 403)
