"""
Ambient request context for the current tenant/branch.

Set by TenantMiddleware at the start of each request and read by
TenantManager/BranchManager so querysets are scoped to the logged-in
user's café even if a view forgets to filter explicitly.
"""
from contextvars import ContextVar

_current_tenant: ContextVar = ContextVar("current_tenant", default=None)
_current_branch: ContextVar = ContextVar("current_branch", default=None)


def set_current_tenant(tenant):
    _current_tenant.set(tenant)


def get_current_tenant():
    return _current_tenant.get()


def set_current_branch(branch):
    _current_branch.set(branch)


def get_current_branch():
    return _current_branch.get()
