from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.core.context import set_current_branch, set_current_tenant
from apps.core.models import AuditLog
from apps.inventory.models import Ingredient, StockItem
from apps.tenants.models import Branch, Cafe

from .models import WastageRecord


class WastageModelTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        self.chicken = Ingredient.objects.create(name="Chicken", unit=Ingredient.Unit.PIECE)
        self.stock = StockItem.objects.create(ingredient=self.chicken, quantity_on_hand=Decimal("10"))
        self.manager = User.objects.create_user(
            email="manager@javas.co", password="pw12345!", role=User.Role.MANAGER, cafe=self.cafe, branch=self.branch
        )

    def tearDown(self):
        set_current_tenant(None)
        set_current_branch(None)

    def test_recording_deducts_stock_immediately(self):
        WastageRecord.objects.create(
            ingredient=self.chicken, quantity=Decimal("3"), reason=WastageRecord.Reason.BURNT
        )
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity_on_hand, Decimal("7"))

    def test_insufficient_stock_raises_and_deducts_nothing(self):
        with self.assertRaises(ValidationError):
            WastageRecord.objects.create(
                ingredient=self.chicken, quantity=Decimal("50"), reason=WastageRecord.Reason.BURNT
            )
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity_on_hand, Decimal("10"))

    def test_approve_marks_status_and_logs_audit(self):
        record = WastageRecord.objects.create(
            ingredient=self.chicken, quantity=Decimal("2"), reason=WastageRecord.Reason.SPOILT
        )
        record.approve(self.manager)
        self.assertEqual(record.status, WastageRecord.Status.APPROVED)
        self.assertEqual(record.approved_by, self.manager)
        self.assertTrue(AuditLog.unscoped.filter(action="wastage.approved").exists())

    def test_reject_restores_stock(self):
        record = WastageRecord.objects.create(
            ingredient=self.chicken, quantity=Decimal("4"), reason=WastageRecord.Reason.DROPPED
        )
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity_on_hand, Decimal("6"))

        record.reject(self.manager)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity_on_hand, Decimal("10"))
        self.assertEqual(record.status, WastageRecord.Status.REJECTED)

    def test_cannot_approve_twice(self):
        record = WastageRecord.objects.create(
            ingredient=self.chicken, quantity=Decimal("1"), reason=WastageRecord.Reason.EXPIRED
        )
        record.approve(self.manager)
        with self.assertRaises(ValidationError):
            record.approve(self.manager)


class WastageApiTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        self.chicken = Ingredient.objects.create(name="Chicken", unit=Ingredient.Unit.PIECE)
        StockItem.objects.create(ingredient=self.chicken, quantity_on_hand=Decimal("10"))
        set_current_tenant(None)
        set_current_branch(None)

        self.chef = User.objects.create_user(
            email="chef@javas.co", password="pw12345!", role=User.Role.CHEF, cafe=self.cafe, branch=self.branch
        )
        self.waiter = User.objects.create_user(
            email="waiter@javas.co", password="pw12345!", role=User.Role.WAITER, cafe=self.cafe, branch=self.branch
        )
        self.manager = User.objects.create_user(
            email="manager@javas.co", password="pw12345!", role=User.Role.MANAGER, cafe=self.cafe, branch=self.branch
        )
        self.client = APIClient()

    def test_chef_can_record_wastage_waiter_cannot(self):
        self.client.login(email="chef@javas.co", password="pw12345!")
        resp = self.client.post(
            "/api/wastage/records/",
            {"ingredient": self.chicken.id, "quantity": "2", "reason": "burnt"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)

        self.client.logout()
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post(
            "/api/wastage/records/",
            {"ingredient": self.chicken.id, "quantity": "1", "reason": "burnt"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_chef_cannot_approve_manager_can(self):
        self.client.login(email="chef@javas.co", password="pw12345!")
        resp = self.client.post(
            "/api/wastage/records/",
            {"ingredient": self.chicken.id, "quantity": "2", "reason": "burnt"},
            format="json",
        )
        record_id = resp.data["id"]

        resp = self.client.post(f"/api/wastage/records/{record_id}/approve/")
        self.assertEqual(resp.status_code, 403)

        self.client.logout()
        self.client.login(email="manager@javas.co", password="pw12345!")
        resp = self.client.post(f"/api/wastage/records/{record_id}/approve/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["status"], "approved")
