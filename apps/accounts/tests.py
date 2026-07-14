from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase

from apps.core.context import get_current_branch, get_current_tenant
from apps.core.middleware import TenantMiddleware
from apps.tenants.models import Branch, Cafe

from .models import User


class UserModelTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas Coffee")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")

    def test_owner_does_not_require_branch(self):
        owner = User(email="owner@javas.co", role=User.Role.OWNER, cafe=self.cafe)
        owner.set_password("s3cret-pass")
        owner.full_clean(exclude=["password"])  # should not raise

    def test_manager_requires_branch(self):
        manager = User(email="manager@javas.co", role=User.Role.MANAGER, cafe=self.cafe)
        manager.set_password("s3cret-pass")
        with self.assertRaises(ValidationError):
            manager.full_clean(exclude=["password"])

    def test_branch_must_belong_to_users_cafe(self):
        other_cafe = Cafe.objects.create(name="2Kings")
        other_branch = Branch.objects.create(tenant=other_cafe, name="Ntinda")
        waiter = User(
            email="waiter@javas.co",
            role=User.Role.WAITER,
            cafe=self.cafe,
            branch=other_branch,
        )
        waiter.set_password("s3cret-pass")
        with self.assertRaises(ValidationError):
            waiter.full_clean(exclude=["password"])

    def test_create_superuser_has_no_cafe_requirement(self):
        admin = User.objects.create_superuser(email="platform@admin.co", password="s3cret-pass")
        self.assertIsNone(admin.cafe)
        self.assertTrue(admin.is_superuser)


class TenantMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.cafe = Cafe.objects.create(name="Javas Coffee")
        self.branch_1 = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        self.branch_2 = Branch.objects.create(tenant=self.cafe, name="Ntinda")

    def _run_middleware(self, request):
        seen = {}

        def get_response(req):
            seen["tenant_in_context"] = get_current_tenant()
            seen["branch_in_context"] = get_current_branch()
            return "response"

        middleware = TenantMiddleware(get_response)
        result = middleware(request)
        return result, seen

    def test_resolves_tenant_and_branch_from_pinned_staff_user(self):
        waiter = User.objects.create_user(
            email="waiter@javas.co",
            password="s3cret-pass",
            role=User.Role.WAITER,
            cafe=self.cafe,
            branch=self.branch_1,
        )
        request = self.factory.get("/")
        request.user = waiter
        request.session = {}

        result, seen = self._run_middleware(request)

        self.assertEqual(result, "response")
        self.assertEqual(request.tenant, self.cafe)
        self.assertEqual(request.branch, self.branch_1)
        self.assertEqual(seen["tenant_in_context"], self.cafe)
        self.assertEqual(seen["branch_in_context"], self.branch_1)
        # context must not leak past the request
        self.assertIsNone(get_current_tenant())
        self.assertIsNone(get_current_branch())

    def test_owner_with_no_pinned_branch_sees_none_by_default(self):
        owner = User.objects.create_user(
            email="owner@javas.co",
            password="s3cret-pass",
            role=User.Role.OWNER,
            cafe=self.cafe,
        )
        request = self.factory.get("/")
        request.user = owner
        request.session = {}

        self._run_middleware(request)

        self.assertEqual(request.tenant, self.cafe)
        self.assertIsNone(request.branch)

    def test_owner_can_select_active_branch_via_session(self):
        owner = User.objects.create_user(
            email="owner2@javas.co",
            password="s3cret-pass",
            role=User.Role.OWNER,
            cafe=self.cafe,
        )
        request = self.factory.get("/")
        request.user = owner
        request.session = {"active_branch_id": self.branch_2.id}

        self._run_middleware(request)

        self.assertEqual(request.branch, self.branch_2)

    def test_anonymous_user_resolves_no_tenant(self):
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.get("/")
        request.user = AnonymousUser()
        request.session = {}

        self._run_middleware(request)

        self.assertIsNone(request.tenant)
        self.assertIsNone(request.branch)
