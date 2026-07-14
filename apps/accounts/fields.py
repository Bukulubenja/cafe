from rest_framework import serializers

from .models import User


class TenantUserField(serializers.PrimaryKeyRelatedField):
    """A writable FK field to `accounts.User`, scoped to the requesting
    user's café.

    `User` is not a TenantModel (no automatic manager-level tenant
    scoping), so any serializer field that lets a client pick an arbitrary
    User by ID -- e.g. "which staff member is this complimentary meal /
    salary record for" -- must use this instead of a plain
    PrimaryKeyRelatedField, or a client could reference a staff member
    belonging to a completely different café.
    """

    def get_queryset(self):
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return User.objects.none()
        return User.objects.filter(cafe=request.user.cafe)
