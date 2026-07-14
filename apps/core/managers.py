from django.db import models

from .context import get_current_branch, get_current_tenant


class TenantManager(models.Manager):
    """Scopes querysets to the current request's tenant.

    Falls back to unscoped when no tenant context is set (management
    commands, shell). Use `.all_tenants()` to explicitly bypass scoping.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = get_current_tenant()
        if tenant is None:
            return qs
        return qs.filter(tenant=tenant)

    def all_tenants(self):
        return super().get_queryset()


class BranchManager(TenantManager):
    """Scopes querysets to the current tenant and, if set, the current branch.

    An owner with no single active branch selected sees all branches
    within their café; staff pinned to one branch only see that branch's data.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        branch = get_current_branch()
        if branch is None:
            return qs
        return qs.filter(branch=branch)
