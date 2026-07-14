from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.core.context import set_current_branch, set_current_tenant
from apps.core.models import AuditLog
from apps.tenants.models import Branch, Cafe

from .models import PayrollRun, SalaryRecord


class SalaryRecordTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        self.waiter = User.objects.create_user(
            email="waiter@javas.co", password="pw12345!", role=User.Role.WAITER, cafe=self.cafe, branch=self.branch
        )

    def test_current_for_picks_most_recent_effective_record(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        SalaryRecord.objects.create(staff=self.waiter, base_salary=Decimal("300000"), effective_date="2026-01-01")
        SalaryRecord.objects.create(staff=self.waiter, base_salary=Decimal("350000"), effective_date="2026-06-01")
        set_current_tenant(None)
        set_current_branch(None)

        current = SalaryRecord.current_for(self.waiter, as_of="2026-07-01")
        self.assertEqual(current.base_salary, Decimal("350000"))

        historical = SalaryRecord.current_for(self.waiter, as_of="2026-03-01")
        self.assertEqual(historical.base_salary, Decimal("300000"))


class PayrollRunTests(TestCase):
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
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        SalaryRecord.objects.create(staff=self.waiter, base_salary=Decimal("300000"), effective_date="2026-01-01")
        SalaryRecord.objects.create(staff=self.chef, base_salary=Decimal("400000"), effective_date="2026-01-01")
        # manager has no salary record configured -> excluded from the run
        set_current_tenant(None)
        set_current_branch(None)

    def test_process_computes_total_and_lines_for_staff_with_a_salary(self):
        run = PayrollRun.process(self.branch, "2026-07-01", "2026-07-31", actor=self.manager)
        self.assertEqual(run.total_paid, Decimal("700000"))
        staff_paid = {line.staff for line in run.lines.all()}
        self.assertEqual(staff_paid, {self.waiter, self.chef})
        self.assertTrue(AuditLog.unscoped.filter(action="payroll.processed").exists())

    def test_cannot_process_same_branch_period_twice(self):
        PayrollRun.process(self.branch, "2026-07-01", "2026-07-31", actor=self.manager)
        with self.assertRaises(ValidationError):
            PayrollRun.process(self.branch, "2026-07-01", "2026-07-31", actor=self.manager)

    def test_rejects_inverted_period(self):
        with self.assertRaises(ValidationError):
            PayrollRun.process(self.branch, "2026-07-31", "2026-07-01", actor=self.manager)


class PayrollApiTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        self.waiter = User.objects.create_user(
            email="waiter@javas.co", password="pw12345!", role=User.Role.WAITER, cafe=self.cafe, branch=self.branch
        )
        self.manager = User.objects.create_user(
            email="manager@javas.co", password="pw12345!", role=User.Role.MANAGER, cafe=self.cafe, branch=self.branch
        )
        self.client = APIClient()

    def test_manager_can_set_salary_waiter_cannot(self):
        self.client.login(email="manager@javas.co", password="pw12345!")
        resp = self.client.post(
            "/api/payroll/salary-records/",
            {"staff": self.waiter.id, "base_salary": "300000", "effective_date": "2026-01-01"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)

        self.client.logout()
        self.client.login(email="waiter@javas.co", password="pw12345!")
        resp = self.client.post(
            "/api/payroll/salary-records/",
            {"staff": self.waiter.id, "base_salary": "999999", "effective_date": "2026-01-01"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_cannot_set_salary_for_staff_in_another_cafe(self):
        other_cafe = Cafe.objects.create(name="2Kings")
        other_branch = Branch.objects.create(tenant=other_cafe, name="Ntinda")
        outsider = User.objects.create_user(
            email="waiter@2kings.co", password="pw12345!", role=User.Role.WAITER, cafe=other_cafe, branch=other_branch
        )

        self.client.login(email="manager@javas.co", password="pw12345!")
        resp = self.client.post(
            "/api/payroll/salary-records/",
            {"staff": outsider.id, "base_salary": "300000", "effective_date": "2026-01-01"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_manager_can_process_payroll_run(self):
        self.client.login(email="manager@javas.co", password="pw12345!")
        self.client.post(
            "/api/payroll/salary-records/",
            {"staff": self.waiter.id, "base_salary": "300000", "effective_date": "2026-01-01"},
            format="json",
        )
        resp = self.client.post(
            "/api/payroll/runs/", {"period_start": "2026-07-01", "period_end": "2026-07-31"}, format="json"
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["total_paid"], "300000.00")
        self.assertEqual(len(resp.data["lines"]), 1)
