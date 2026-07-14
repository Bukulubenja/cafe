from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def broadcast_kitchen_update(order_item):
    """Pushes an OrderItem's current kitchen-ticket state to that branch's
    live kitchen feed (see consumers.KitchenConsumer). Called from
    synchronous model code, so uses async_to_sync -- the documented pattern
    for triggering channel-layer sends from outside async views/consumers.

    No-op if no channel layer is configured (e.g. in a plain script/shell).
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    # Imported here, not at module level: serializers.py doesn't depend on
    # this module, so this just avoids a needless import at Django startup
    # for code that isn't always exercised (e.g. management commands).
    from .serializers import KitchenTicketSerializer

    async_to_sync(channel_layer.group_send)(
        f"kitchen_branch_{order_item.branch_id}",
        {"type": "kitchen.update", "ticket": KitchenTicketSerializer(order_item).data},
    )
