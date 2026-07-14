from .context import set_current_branch, set_current_tenant


class TenantMiddleware:
    """Derives the active café/branch from the logged-in user.

    Must run after AuthenticationMiddleware (request.user must exist).
    Exposes request.tenant / request.branch, and sets the ambient context
    read by TenantManager/BranchManager, so querysets stay scoped even if
    a view forgets to filter explicitly. Context is always cleared at the
    end of the request (even on exceptions) so it can never leak into a
    later request handled by the same worker thread.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        tenant = None
        branch = None

        if user is not None and user.is_authenticated:
            tenant = getattr(user, "cafe", None)
            branch = getattr(user, "branch", None)

            if branch is None and tenant is not None:
                active_branch_id = request.session.get("active_branch_id")
                if active_branch_id:
                    branch = tenant.branches.filter(id=active_branch_id).first()

        request.tenant = tenant
        request.branch = branch
        set_current_tenant(tenant)
        set_current_branch(branch)

        try:
            return self.get_response(request)
        finally:
            set_current_tenant(None)
            set_current_branch(None)
