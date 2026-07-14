from django.db import models

from .context import get_current_branch, get_current_tenant
from .managers import BranchManager, TenantManager


class TenantModel(models.Model):
    """Abstract base for any model owned by a single café (tenant).

    `objects` is tenant-scoped by default; `unscoped` bypasses scoping for
    admin tooling and cross-tenant reporting only.
    """

    tenant = models.ForeignKey(
        "tenants.Cafe",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    objects = TenantManager()
    unscoped = models.Manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.tenant_id is None:
            tenant = get_current_tenant()
            if tenant is not None:
                self.tenant = tenant
        super().save(*args, **kwargs)


class BranchModel(TenantModel):
    """Abstract base for models owned by one branch of a café.

    Auto-fills `tenant` from the branch when not set explicitly.
    """

    branch = models.ForeignKey(
        "tenants.Branch",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    objects = BranchManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.branch_id is None:
            branch = get_current_branch()
            if branch is not None:
                self.branch = branch
        if self.tenant_id is None and self.branch_id is not None:
            self.tenant_id = self.branch.tenant_id
        super().save(*args, **kwargs)


class AuditLog(BranchModel):
    """Records who did what, where, and when -- the readme calls for owners
    to view audit logs and for every transaction/adjustment to be traceable
    to a staff member and branch (shift accountability).
    """

    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=100)
    object_repr = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} by {self.actor} @ {self.branch}"
