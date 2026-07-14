import uuid as uuid_lib

from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.tenants.models import Branch


def parse_client_id(request_data):
    """Validates an optional client-generated UUID used for idempotent
    offline-sync retries (a client queues a create while offline, then may
    resend it after reconnecting without knowing if the first attempt
    landed). Returns None if not provided; raises 400 if malformed.
    """
    raw = request_data.get("client_id")
    if not raw:
        return None
    try:
        return uuid_lib.UUID(str(raw))
    except (ValueError, AttributeError, TypeError):
        raise DRFValidationError({"client_id": "Must be a valid UUID."})


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
