import json
from decimal import Decimal

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase

from apps.accounts.models import User
from apps.core.context import set_current_branch, set_current_tenant
from apps.menu.models import Category, MenuItem
from apps.tenants.models import Branch, Cafe

from .consumers import KitchenConsumer
from .models import Order, OrderItem, Table


class KitchenConsumerTests(TransactionTestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        self.chef = User.objects.create_user(
            email="chef@javas.co", password="pw12345!", role=User.Role.CHEF, cafe=self.cafe, branch=self.branch
        )
        self.owner = User.objects.create_user(
            email="owner@javas.co", password="pw12345!", role=User.Role.OWNER, cafe=self.cafe
        )

    @database_sync_to_async
    def _create_kitchen_ticket(self):
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        category = Category.objects.create(name="Lunch")
        menu_item = MenuItem.objects.create(category=category, name="Chicken Pilau", selling_price=Decimal("15000"))
        table = Table.objects.create(name="T1")
        order = Order.objects.create(table=table)
        item = OrderItem.objects.create(order=order, menu_item=menu_item, quantity=1)
        set_current_tenant(None)
        set_current_branch(None)
        return item

    async def test_authenticated_chef_connects(self):
        communicator = WebsocketCommunicator(KitchenConsumer.as_asgi(), "/ws/kitchen/")
        communicator.scope["user"] = self.chef
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_unauthenticated_connection_rejected(self):
        communicator = WebsocketCommunicator(KitchenConsumer.as_asgi(), "/ws/kitchen/")
        communicator.scope["user"] = AnonymousUser()
        connected, _ = await communicator.connect()
        self.assertFalse(connected)

    async def test_owner_with_no_branch_and_no_query_param_rejected(self):
        communicator = WebsocketCommunicator(KitchenConsumer.as_asgi(), "/ws/kitchen/")
        communicator.scope["user"] = self.owner
        connected, _ = await communicator.connect()
        self.assertFalse(connected)

    async def test_owner_can_connect_with_branch_query_param(self):
        communicator = WebsocketCommunicator(
            KitchenConsumer.as_asgi(), f"/ws/kitchen/?branch={self.branch.id}"
        )
        communicator.scope["user"] = self.owner
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_receives_broadcast_when_kitchen_ticket_created(self):
        communicator = WebsocketCommunicator(KitchenConsumer.as_asgi(), "/ws/kitchen/")
        communicator.scope["user"] = self.chef
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        item = await self._create_kitchen_ticket()

        message = await communicator.receive_from()
        data = json.loads(message)
        self.assertEqual(data["id"], item.id)
        self.assertEqual(data["kitchen_status"], "pending")

        await communicator.disconnect()

    async def test_receives_broadcast_on_status_transition(self):
        item = await self._create_kitchen_ticket()

        communicator = WebsocketCommunicator(KitchenConsumer.as_asgi(), "/ws/kitchen/")
        communicator.scope["user"] = self.chef
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        await database_sync_to_async(item.mark_cooking)()

        message = await communicator.receive_from()
        data = json.loads(message)
        self.assertEqual(data["id"], item.id)
        self.assertEqual(data["kitchen_status"], "cooking")

        await communicator.disconnect()
