import json
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from apps.accounts.models import User

ALLOWED_ROLES = {
    User.Role.OWNER,
    User.Role.MANAGER,
    User.Role.CHEF,
    User.Role.WAITER,
    User.Role.CASHIER,
}


class KitchenConsumer(AsyncWebsocketConsumer):
    """Live kitchen ticket feed for one branch -- pushes updates instead of
    the client having to poll GET /api/pos/kitchen/queue/. Branch
    resolution mirrors apps.core.utils.resolve_acting_branch: staff pinned
    to one branch use it automatically; an Owner (no fixed branch) must
    connect with ?branch=<id>.
    """

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return

        if not user.is_superuser and user.role not in ALLOWED_ROLES:
            await self.close(code=4403)
            return

        branch = await self._resolve_branch(user)
        if branch is None:
            await self.close(code=4400)
            return

        self.group_name = f"kitchen_branch_{branch.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def kitchen_update(self, event):
        await self.send(text_data=json.dumps(event["ticket"]))

    @database_sync_to_async
    def _resolve_branch(self, user):
        if user.branch_id:
            return user.branch

        query = parse_qs(self.scope.get("query_string", b"").decode())
        branch_ids = query.get("branch")
        if not branch_ids:
            return None

        from apps.tenants.models import Branch

        return Branch.objects.filter(pk=branch_ids[0], tenant_id=user.cafe_id).first()
