from django.test import TestCase

from apps.tenants.models import Branch, Cafe

from .context import get_current_branch, get_current_tenant, set_current_branch, set_current_tenant
from .models import AuditLog


class TenantManagerScopingTests(TestCase):
    def setUp(self):
        self.cafe_a = Cafe.objects.create(name="Cafe A")
        self.cafe_b = Cafe.objects.create(name="Cafe B")
        self.branch_a = Branch.objects.create(tenant=self.cafe_a, name="A Main")
        self.branch_b = Branch.objects.create(tenant=self.cafe_b, name="B Main")
        AuditLog.unscoped.create(tenant=self.cafe_a, branch=self.branch_a, action="a-event")
        AuditLog.unscoped.create(tenant=self.cafe_b, branch=self.branch_b, action="b-event")

    def tearDown(self):
        set_current_tenant(None)
        set_current_branch(None)

    def test_no_context_is_unscoped(self):
        self.assertIsNone(get_current_tenant())
        self.assertEqual(AuditLog.objects.count(), 2)

    def test_scopes_to_current_tenant(self):
        set_current_tenant(self.cafe_a)
        actions = list(AuditLog.objects.values_list("action", flat=True))
        self.assertEqual(actions, ["a-event"])

    def test_unscoped_manager_always_sees_everything(self):
        set_current_tenant(self.cafe_a)
        self.assertEqual(AuditLog.unscoped.count(), 2)

    def test_save_autofills_tenant_from_context(self):
        set_current_tenant(self.cafe_a)
        log = AuditLog(branch=self.branch_a, action="implicit-tenant")
        log.save()
        self.assertEqual(log.tenant_id, self.cafe_a.id)


class BranchManagerScopingTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch_1 = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        self.branch_2 = Branch.objects.create(tenant=self.cafe, name="Ntinda")
        AuditLog.unscoped.create(tenant=self.cafe, branch=self.branch_1, action="b1-event")
        AuditLog.unscoped.create(tenant=self.cafe, branch=self.branch_2, action="b2-event")

    def tearDown(self):
        set_current_tenant(None)
        set_current_branch(None)

    def test_owner_with_no_branch_selected_sees_all_branches(self):
        set_current_tenant(self.cafe)
        self.assertEqual(AuditLog.objects.count(), 2)

    def test_staff_pinned_to_branch_sees_only_that_branch(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch_1)
        actions = list(AuditLog.objects.values_list("action", flat=True))
        self.assertEqual(actions, ["b1-event"])

    def test_save_autofills_branch_and_tenant_from_context(self):
        set_current_branch(self.branch_1)
        log = AuditLog(action="implicit-branch")
        log.save()
        self.assertEqual(log.branch_id, self.branch_1.id)
        self.assertEqual(log.tenant_id, self.cafe.id)


class TenantContextTests(TestCase):
    def tearDown(self):
        set_current_tenant(None)
        set_current_branch(None)

    def test_context_defaults_to_none_and_round_trips(self):
        self.assertIsNone(get_current_tenant())
        self.assertIsNone(get_current_branch())

        cafe = Cafe.objects.create(name="Round Trip Cafe")
        set_current_tenant(cafe)
        self.assertEqual(get_current_tenant(), cafe)
