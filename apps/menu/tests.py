from decimal import Decimal

from django.test import TestCase

from apps.core.context import set_current_branch, set_current_tenant
from apps.inventory.models import Ingredient, RecipeItem, StockItem
from apps.tenants.models import Branch, Cafe

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


class MenuItemAvailabilityTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        self.category = Category.objects.create(name="Lunch")

    def tearDown(self):
        set_current_tenant(None)
        set_current_branch(None)

    def test_no_recipe_is_always_available(self):
        item = MenuItem.objects.create(category=self.category, name="Bottled Water", selling_price=Decimal("2000"))
        self.assertTrue(item.is_available_at(self.branch))

    def test_manual_flag_off_overrides_stock(self):
        item = MenuItem.objects.create(
            category=self.category, name="Seasonal", selling_price=Decimal("2000"), is_available=False
        )
        self.assertFalse(item.is_available_at(self.branch))

    def test_unavailable_when_recipe_ingredient_short(self):
        chicken = Ingredient.objects.create(name="Chicken", unit=Ingredient.Unit.PIECE)
        StockItem.objects.create(ingredient=chicken, quantity_on_hand=Decimal("0"))
        item = MenuItem.objects.create(category=self.category, name="Chicken Pilau", selling_price=Decimal("15000"))
        RecipeItem.objects.create(menu_item=item, ingredient=chicken, quantity_required=Decimal("1"))

        self.assertFalse(item.is_available_at(self.branch))

    def test_available_when_stock_sufficient(self):
        chicken = Ingredient.objects.create(name="Chicken", unit=Ingredient.Unit.PIECE)
        StockItem.objects.create(ingredient=chicken, quantity_on_hand=Decimal("5"))
        item = MenuItem.objects.create(category=self.category, name="Chicken Pilau", selling_price=Decimal("15000"))
        RecipeItem.objects.create(menu_item=item, ingredient=chicken, quantity_required=Decimal("1"))

        self.assertTrue(item.is_available_at(self.branch))

    def test_availability_is_per_branch(self):
        other_branch = Branch.objects.create(tenant=self.cafe, name="Ntinda")
        chicken = Ingredient.objects.create(name="Chicken", unit=Ingredient.Unit.PIECE)
        StockItem.objects.create(ingredient=chicken, quantity_on_hand=Decimal("5"))  # this branch has stock
        item = MenuItem.objects.create(category=self.category, name="Chicken Pilau", selling_price=Decimal("15000"))
        RecipeItem.objects.create(menu_item=item, ingredient=chicken, quantity_required=Decimal("1"))

        self.assertTrue(item.is_available_at(self.branch))
        self.assertFalse(item.is_available_at(other_branch))  # no StockItem at all there
