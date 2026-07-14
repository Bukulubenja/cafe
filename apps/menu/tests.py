from decimal import Decimal

from django.test import TestCase

from apps.core.context import set_current_tenant
from apps.tenants.models import Cafe

from .models import Category, MenuItem


class MenuItemTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        set_current_tenant(self.cafe)
        self.category = Category.objects.create(name="Breakfast")

    def tearDown(self):
        set_current_tenant(None)

    def test_profit_margin(self):
        item = MenuItem.objects.create(
            category=self.category, name="Rolex", selling_price=Decimal("8000"), cost_price=Decimal("3000")
        )
        self.assertEqual(item.profit_margin, Decimal("5000"))

    def test_vat_and_price_including_vat(self):
        item = MenuItem.objects.create(
            category=self.category,
            name="Chicken Pilau",
            selling_price=Decimal("15000"),
            cost_price=Decimal("6000"),
            vat_rate=Decimal("18.00"),
        )
        self.assertEqual(item.vat_amount, Decimal("2700.00"))
        self.assertEqual(item.price_including_vat, Decimal("17700.00"))

    def test_menu_item_scoped_to_tenant(self):
        other_cafe = Cafe.objects.create(name="2Kings")
        set_current_tenant(other_cafe)
        other_category = Category.objects.create(name="Lunch")
        MenuItem.objects.create(category=other_category, name="Matooke", selling_price=Decimal("5000"))

        set_current_tenant(self.cafe)
        MenuItem.objects.create(category=self.category, name="Tea", selling_price=Decimal("2000"))

        names = list(MenuItem.objects.values_list("name", flat=True))
        self.assertEqual(names, ["Tea"])
