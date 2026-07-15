from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.core.context import set_current_branch, set_current_tenant
from apps.tenants.models import Branch, Cafe

from .models import Shift


class ShiftModelTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        self.waiter = User.objects.create_user(
            email="waiter@javas.co", password="pw12345!", role=User.Role.WAITER, cafe=self.cafe, branch=self.branch
        )

    def test_open_for_rejects_a_second_open_shift(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        Shift.open_for(self.waiter, self.branch)
        with self.assertRaises(ValidationError):
            Shift.open_for(self.waiter, self.branch)
        set_current_tenant(None)
        set_current_branch(None)

    def test_current_for_returns_none_once_closed(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        shift = Shift.open_for(self.waiter, self.branch)
        self.assertEqual(Shift.current_for(self.waiter), shift)
        shift.close(self.waiter)
        self.assertIsNone(Shift.current_for(self.waiter))
        set_current_tenant(None)
        set_current_branch(None)

    def test_cannot_close_an_already_closed_shift(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        shift = Shift.open_for(self.waiter, self.branch)
        shift.close(self.waiter)
        with self.assertRaises(ValidationError):
            shift.close(self.waiter)
        set_current_tenant(None)
        set_current_branch(None)


class ShiftApiTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
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

    def test_waiter_clocks_in_and_out(self):
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post("/api/shifts/shifts/")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(resp.data["is_open"])
        shift_id = resp.data["id"]

        resp = self.client.post(f"/api/shifts/shifts/{shift_id}/close/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertFalse(resp.data["is_open"])

    def test_second_clock_in_while_open_rejected(self):
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post("/api/shifts/shifts/")
        self.assertEqual(resp.status_code, 201, resp.content)
        resp = self.client.post("/api/shifts/shifts/")
        self.assertEqual(resp.status_code, 400)

    def test_non_manager_cannot_close_someone_elses_shift(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        shift = Shift.open_for(self.waiter, self.branch)
        set_current_tenant(None)
        set_current_branch(None)

        # get_queryset() scopes non-managers to their own shifts, so a
        # chef requesting the waiter's shift 404s rather than 403ing --
        # it doesn't exist from the chef's point of view.
        self.client.login(email="chef@javas.co", password="pw12345!")
        resp = self.client.post(f"/api/shifts/shifts/{shift.id}/close/")
        self.assertEqual(resp.status_code, 404)

    def test_manager_can_close_someone_elses_shift(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        shift = Shift.open_for(self.waiter, self.branch)
        set_current_tenant(None)
        set_current_branch(None)

        self.client.login(email="manager@javas.co", password="pw12345!")
        resp = self.client.post(f"/api/shifts/shifts/{shift.id}/close/")
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_non_manager_only_sees_own_shifts(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        Shift.open_for(self.waiter, self.branch)
        Shift.open_for(self.chef, self.branch)
        set_current_tenant(None)
        set_current_branch(None)

        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.get("/api/shifts/shifts/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["staff_email"], "waiter@javas.co")

        self.client.logout()
        self.client.login(email="manager@javas.co", password="pw12345!")
        resp = self.client.get("/api/shifts/shifts/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 2)
