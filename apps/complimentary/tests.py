from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.core.context import set_current_branch, set_current_tenant
from apps.core.models import AuditLog
from apps.inventory.models import Ingredient, RecipeItem, StockItem
from apps.menu.models import Category, MenuItem
from apps.tenants.models import Branch, Cafe

from .models import ComplimentaryMeal


class ComplimentaryMealModelTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)

        self.tea_leaves = Ingredient.objects.create(name="Tea Leaves", unit=Ingredient.Unit.GRAM)
        self.stock = StockItem.objects.create(ingredient=self.tea_leaves, quantity_on_hand=Decimal("500"))

        category = Category.objects.create(name="Breakfast")
        self.tea = MenuItem.objects.create(
            category=category, name="Tea", selling_price=Decimal("2000"), cost_price=Decimal("500")
        )
        RecipeItem.objects.create(menu_item=self.tea, ingredient=self.tea_leaves, quantity_required=Decimal("10"))

        self.manager = User.objects.create_user(
            email="manager@javas.co", password="pw12345!", role=User.Role.MANAGER, cafe=self.cafe, branch=self.branch
        )
        self.waiter = User.objects.create_user(
            email="waiter@javas.co", password="pw12345!", role=User.Role.WAITER, cafe=self.cafe, branch=self.branch
        )

    def tearDown(self):
        set_current_tenant(None)
        set_current_branch(None)

    def test_creation_does_not_deduct_stock(self):
        ComplimentaryMeal.objects.create(
            staff=self.waiter,
            menu_item=self.tea,
            quantity=2,
            reason=ComplimentaryMeal.Reason.WAITER_BREAKFAST,
            requested_by=self.waiter,
        )
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity_on_hand, Decimal("500"))

    def test_approve_deducts_stock_and_snapshots_cost(self):
        meal = ComplimentaryMeal.objects.create(
            staff=self.waiter,
            menu_item=self.tea,
            quantity=2,
            reason=ComplimentaryMeal.Reason.WAITER_BREAKFAST,
            requested_by=self.waiter,
        )
        meal.approve(self.manager)

        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity_on_hand, Decimal("480"))  # 500 - 10*2
        self.assertEqual(meal.status, ComplimentaryMeal.Status.APPROVED)
        self.assertEqual(meal.unit_cost, Decimal("500"))
        self.assertEqual(meal.total_cost, Decimal("1000"))
        self.assertTrue(AuditLog.unscoped.filter(action="complimentary.approved").exists())

    def test_reject_does_not_deduct_stock(self):
        meal = ComplimentaryMeal.objects.create(
            staff=self.waiter,
            menu_item=self.tea,
            quantity=2,
            reason=ComplimentaryMeal.Reason.PROMOTION,
            requested_by=self.waiter,
        )
        meal.reject(self.manager)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity_on_hand, Decimal("500"))
        self.assertEqual(meal.status, ComplimentaryMeal.Status.REJECTED)

    def test_approve_fails_on_insufficient_stock_and_stays_pending(self):
        meal = ComplimentaryMeal.objects.create(
            staff=self.waiter,
            menu_item=self.tea,
            quantity=100,  # needs 1000g, only 500g in stock
            reason=ComplimentaryMeal.Reason.VIP,
            requested_by=self.waiter,
        )
        with self.assertRaises(ValidationError):
            meal.approve(self.manager)
        meal.refresh_from_db()
        self.assertEqual(meal.status, ComplimentaryMeal.Status.PENDING)

    def test_cannot_approve_twice(self):
        meal = ComplimentaryMeal.objects.create(
            staff=self.waiter,
            menu_item=self.tea,
            quantity=1,
            reason=ComplimentaryMeal.Reason.CHEF_TEA,
            requested_by=self.waiter,
        )
        meal.approve(self.manager)
        with self.assertRaises(ValidationError):
            meal.approve(self.manager)


class ComplimentaryMealApiTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        category = Category.objects.create(name="Breakfast")
        self.tea = MenuItem.objects.create(category=category, name="Tea", selling_price=Decimal("2000"))
        set_current_tenant(None)
        set_current_branch(None)

        self.waiter = User.objects.create_user(
            email="waiter@javas.co", password="pw12345!", role=User.Role.WAITER, cafe=self.cafe, branch=self.branch
        )
        self.chef = User.objects.create_user(
            email="chef@javas.co", password="pw12345!", role=User.Role.CHEF, cafe=self.cafe, branch=self.branch
        )
        self.manager = User.objects.create_user(
            email="manager@javas.co", password="pw12345!", role=User.Role.MANAGER, cafe=self.cafe, branch=self.branch
        )
        self.client = APIClient()

    def test_any_staff_role_can_file_a_request(self):
        self.client.login(email="chef@javas.co", password="pw12345!")
        resp = self.client.post(
            "/api/complimentary/meals/",
            {"menu_item": self.tea.id, "quantity": 1, "reason": "chef_tea"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_cannot_assign_staff_from_another_cafe(self):
        other_cafe = Cafe.objects.create(name="2Kings")
        other_branch = Branch.objects.create(tenant=other_cafe, name="Ntinda")
        outsider = User.objects.create_user(
            email="waiter@2kings.co", password="pw12345!", role=User.Role.WAITER, cafe=other_cafe, branch=other_branch
        )

        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post(
            "/api/complimentary/meals/",
            {"menu_item": self.tea.id, "quantity": 1, "reason": "waiter_breakfast", "staff": outsider.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_waiter_cannot_approve_manager_can(self):
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post(
            "/api/complimentary/meals/",
            {"menu_item": self.tea.id, "quantity": 1, "reason": "waiter_breakfast"},
            format="json",
        )
        meal_id = resp.data["id"]

        resp = self.client.post(f"/api/complimentary/meals/{meal_id}/approve/")
        self.assertEqual(resp.status_code, 403)

        self.client.logout()
        self.client.login(email="manager@javas.co", password="pw12345!")
        resp = self.client.post(f"/api/complimentary/meals/{meal_id}/approve/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["status"], "approved")
