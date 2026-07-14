from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.core.context import set_current_branch, set_current_tenant
from apps.core.models import AuditLog
from apps.menu.models import Category, MenuItem
from apps.tenants.models import Branch, Cafe

from .models import Ingredient, RecipeItem, StockItem
from .services import deduct_stock_for_order_item


class InventoryModelTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)
        self.rice = Ingredient.objects.create(name="Rice", category=Ingredient.Category.KITCHEN, unit=Ingredient.Unit.GRAM)

    def tearDown(self):
        set_current_tenant(None)
        set_current_branch(None)

    def test_is_low_stock(self):
        stock = StockItem.objects.create(ingredient=self.rice, quantity_on_hand=Decimal("400"), minimum_quantity=Decimal("500"))
        self.assertTrue(stock.is_low_stock)
        stock.quantity_on_hand = Decimal("600")
        self.assertFalse(stock.is_low_stock)

    def test_ingredient_scoped_to_tenant(self):
        other_cafe = Cafe.objects.create(name="2Kings")
        set_current_tenant(other_cafe)
        Ingredient.objects.create(name="Rice", unit=Ingredient.Unit.GRAM)

        set_current_tenant(self.cafe)
        names = list(Ingredient.objects.values_list("name", flat=True))
        self.assertEqual(names, ["Rice"])

    def test_stock_item_scoped_to_branch(self):
        other_branch = Branch.objects.create(tenant=self.cafe, name="Ntinda")
        StockItem.unscoped.create(tenant=self.cafe, branch=other_branch, ingredient=self.rice, quantity_on_hand=Decimal("10"))
        StockItem.objects.create(ingredient=self.rice, quantity_on_hand=Decimal("20"))

        set_current_branch(self.branch)
        qtys = list(StockItem.objects.values_list("quantity_on_hand", flat=True))
        self.assertEqual(qtys, [Decimal("20")])

    def test_whatsapp_alert_fires_once_on_crossing_into_low_stock_not_on_every_save(self):
        from apps.accounts.models import User
        from apps.notifications.models import NotificationLog

        User.objects.create_user(
            email="owner@javas.co", password="pw12345!", role=User.Role.OWNER, cafe=self.cafe, phone="0700000001"
        )
        stock = StockItem.objects.create(
            ingredient=self.rice, quantity_on_hand=Decimal("500"), minimum_quantity=Decimal("100")
        )
        self.assertEqual(NotificationLog.objects.count(), 0)  # well above minimum, no alert yet

        stock.quantity_on_hand = Decimal("50")
        stock.save()  # crosses into low stock -> alerts once
        self.assertEqual(NotificationLog.objects.count(), 1)

        stock.quantity_on_hand = Decimal("20")
        stock.save()  # still low stock -> no repeat alert
        self.assertEqual(NotificationLog.objects.count(), 1)


class StockDeductionTests(TestCase):
    def setUp(self):
        self.cafe = Cafe.objects.create(name="Javas")
        self.branch = Branch.objects.create(tenant=self.cafe, name="Kampala Rd")
        set_current_tenant(self.cafe)
        set_current_branch(self.branch)

        self.rice = Ingredient.objects.create(name="Rice", unit=Ingredient.Unit.GRAM)
        self.chicken = Ingredient.objects.create(name="Chicken", unit=Ingredient.Unit.PIECE)

        self.rice_stock = StockItem.objects.create(ingredient=self.rice, quantity_on_hand=Decimal("1000"))
        self.chicken_stock = StockItem.objects.create(ingredient=self.chicken, quantity_on_hand=Decimal("5"))

        category = Category.objects.create(name="Lunch")
        self.pilau = MenuItem.objects.create(category=category, name="Chicken Pilau", selling_price=Decimal("15000"))
        RecipeItem.objects.create(menu_item=self.pilau, ingredient=self.rice, quantity_required=Decimal("300"))
        RecipeItem.objects.create(menu_item=self.pilau, ingredient=self.chicken, quantity_required=Decimal("1"))

        self.no_recipe_item = MenuItem.objects.create(category=category, name="Bottled Water", selling_price=Decimal("2000"))

    def tearDown(self):
        set_current_tenant(None)
        set_current_branch(None)

    def _fake_order_item(self, menu_item, quantity):
        # Deduction only needs these attributes; avoids depending on apps.pos here.
        class _Fake:
            pass

        fake = _Fake()
        fake.menu_item = menu_item
        fake.quantity = quantity
        fake.branch = self.branch
        fake.tenant = self.cafe
        return fake

    def test_deducts_all_ingredients_for_quantity(self):
        order_item = self._fake_order_item(self.pilau, 2)
        deduct_stock_for_order_item(order_item)

        self.rice_stock.refresh_from_db()
        self.chicken_stock.refresh_from_db()
        self.assertEqual(self.rice_stock.quantity_on_hand, Decimal("400"))  # 1000 - 300*2
        self.assertEqual(self.chicken_stock.quantity_on_hand, Decimal("3"))  # 5 - 1*2

    def test_logs_audit_entry(self):
        order_item = self._fake_order_item(self.pilau, 1)
        deduct_stock_for_order_item(order_item)
        self.assertTrue(AuditLog.unscoped.filter(action="stock.deducted").exists())

    def test_insufficient_stock_deducts_nothing(self):
        order_item = self._fake_order_item(self.pilau, 10)  # needs 10 chicken, only 5 in stock
        with self.assertRaises(ValidationError):
            deduct_stock_for_order_item(order_item)

        self.rice_stock.refresh_from_db()
        self.chicken_stock.refresh_from_db()
        self.assertEqual(self.rice_stock.quantity_on_hand, Decimal("1000"))
        self.assertEqual(self.chicken_stock.quantity_on_hand, Decimal("5"))

    def test_no_recipe_is_a_noop(self):
        order_item = self._fake_order_item(self.no_recipe_item, 5)
        deduct_stock_for_order_item(order_item)  # should not raise
