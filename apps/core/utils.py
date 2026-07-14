from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.tenants.models import Branch


def resolve_acting_branch(user, request_data):
    """Resolve which branch a create-type action applies to.

    Staff other than Owner are always pinned to one branch. An Owner has no
    fixed branch, so they must specify `branch` explicitly in the request body.
    """
    branch = user.branch
    if branch is not None:
        return branch

    branch_id = request_data.get("branch")
    if not branch_id:
        raise DRFValidationError(
            {"branch": "Required: you have no fixed branch, so specify which branch this is for."}
        )
    branch = Branch.objects.filter(pk=branch_id, tenant=user.cafe).first()
    if branch is None:
        raise DRFValidationError({"branch": "Invalid branch for this café."})
    return branch
