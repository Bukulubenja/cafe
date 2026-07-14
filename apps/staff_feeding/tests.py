from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.core.context import set_current_branch, set_current_tenant
from apps.inventory.models import Ingredient, RecipeItem, StockItem
from apps.menu.models import Category, MenuItem
from apps.tenants.models import Branch, Cafe

from .models import FeedingRecord, FeedingSlot


class FeedingRecordModelTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)

        self.slot = FeedingSlot.objects.create(name=FeedingSlot.Name.LUNCH)
        self.tea_leaves = Ingredient.objects.create(name="Tea Leaves", unit=Ingredient.Unit.GRAM)
        self.stock = StockItem.objects.create(ingredient=self.tea_leaves, quantity_on_hand=Decimal("100"))
        category = Category.objects.create(name="Breakfast")
        self.tea = MenuItem.objects.create(
            category=category, name="Tea", selling_price=Decimal("1000"), cost_price=Decimal("300")
        )
        RecipeItem.objects.create(menu_item=self.tea, ingredient=self.tea_leaves, quantity_required=Decimal("10"))

        self.waiter = User.objects.create_user(
            email="waiter@javas.co", password="pw12345!", role=User.Role.WAITER, cafe=self.cafe, branch=self.branch
        )

    def tearDown(self):
        set_current_tenant(None)
        set_current_branch(None)

    def test_creation_deducts_stock_and_snapshots_cost(self):
        record = FeedingRecord.objects.create(staff=self.waiter, slot=self.slot, menu_item=self.tea)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity_on_hand, Decimal("90"))
        self.assertEqual(record.unit_cost, Decimal("300"))

    def test_insufficient_stock_rolls_back_creation(self):
        StockItem.objects.filter(pk=self.stock.pk).update(quantity_on_hand=Decimal("1"))
        with self.assertRaises(ValidationError):
            FeedingRecord.objects.create(staff=self.waiter, slot=self.slot, menu_item=self.tea)
        self.assertEqual(FeedingRecord.objects.count(), 0)

    def test_duplicate_same_staff_slot_day_rejected(self):
        from django.db import IntegrityError

        FeedingRecord.objects.create(staff=self.waiter, slot=self.slot, menu_item=self.tea)
        with self.assertRaises(IntegrityError):
            FeedingRecord.objects.create(staff=self.waiter, slot=self.slot, menu_item=self.tea)


class FeedingRecordApiTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        self.slot = FeedingSlot.objects.create(name=FeedingSlot.Name.MORNING_TEA)
        category = Category.objects.create(name="Breakfast")
        self.tea = MenuItem.objects.create(category=category, name="Tea", selling_price=Decimal("1000"))
        tea_leaves = Ingredient.objects.create(name="Tea Leaves", unit=Ingredient.Unit.GRAM)
        StockItem.objects.create(ingredient=tea_leaves, quantity_on_hand=Decimal("1000"))
        RecipeItem.objects.create(menu_item=self.tea, ingredient=tea_leaves, quantity_required=Decimal("10"))
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

    def test_staff_can_log_own_record(self):
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post(
            "/api/staff-feeding/records/", {"slot": self.slot.id, "menu_item": self.tea.id}, format="json"
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["staff_email"], "waiter@javas.co")

    def test_staff_cannot_log_record_for_someone_else(self):
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post(
            "/api/staff-feeding/records/",
            {"slot": self.slot.id, "menu_item": self.tea.id, "staff": self.chef.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        # staff is force-set to the requester regardless of what was submitted
        self.assertEqual(resp.data["staff_email"], "waiter@javas.co")

    def test_staff_only_sees_own_records_manager_sees_all(self):
        self.client.login(email="waiter@javas.co", password="pw12345!")
        self.client.post("/api/staff-feeding/records/", {"slot": self.slot.id, "menu_item": self.tea.id}, format="json")
        self.client.logout()

        self.client.login(email="chef@javas.co", password="pw12345!")
        resp = self.client.get("/api/staff-feeding/records/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 0)  # chef hasn't logged anything, and can't see waiter's

        self.client.logout()
        self.client.login(email="manager@javas.co", password="pw12345!")
        resp = self.client.get("/api/staff-feeding/records/")
        self.assertEqual(len(resp.data), 1)  # manager sees everyone's

    def test_only_manager_can_manage_slots(self):
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post("/api/staff-feeding/slots/", {"name": "evening_tea"}, format="json")
        self.assertEqual(resp.status_code, 403)

        self.client.logout()
        self.client.login(email="manager@javas.co", password="pw12345!")
        resp = self.client.post("/api/staff-feeding/slots/", {"name": "evening_tea"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
