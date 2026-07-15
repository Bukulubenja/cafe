import csv

from django.http import HttpResponse

from apps.core.context import set_current_branch
from apps.tenants.models import Branch


def resolve_branch(request):
    """Which branch a page should show. Staff pinned to one branch always
    see it; an Owner (no fixed branch) can pass ?branch=<id>, defaulting to
    their café's first branch otherwise. Returns None only if the café
    genuinely has no branches yet.

    TenantMiddleware already set the ambient branch context for this
    request before the view ran, from the session's `active_branch_id` --
    but that's only populated *after* an Owner has picked a branch once. So
    this also updates the session (for future requests) and re-applies the
    context right now (for BranchManager-scoped queries made later in this
    same view), rather than only fixing it from the next request onward.
    """
    user = request.user
    if user.branch_id:
        return user.branch

    branch_id = request.GET.get("branch")
    branch = None
    if branch_id:
        branch = Branch.objects.filter(pk=branch_id, tenant=user.cafe).first()
    if branch is None:
        branch = Branch.objects.filter(tenant=user.cafe).order_by("name").first()

    if branch is not None:
        request.session["active_branch_id"] = branch.id
        set_current_branch(branch)
    return branch


def friendly_error(exc):
    """Renders a Django ValidationError as one line for a messages.error() call."""
    return "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)


def csv_response(filename, header, rows):
    """A downloadable CSV for an auditor: one header row, then `rows`
    (any iterable of iterables -- values are stringified by csv.writer).
    """
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(header)
    writer.writerows(rows)
    return response
