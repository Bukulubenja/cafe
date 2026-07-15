"""readme's Ugandan Menu Templates differentiator: ready-made starter
menus an owner can apply to their café, each with suggested categories,
recipes, and stock items -- rather than starting from a blank menu.

There's no self-serve café signup flow in this codebase yet (cafés are
created via /admin/), so this isn't gated to "at café creation" as the
readme frames it; it's exposed as an apply-anytime action on an existing
café instead, which is a strict superset of the readme's ask and doesn't
lose anything -- an owner can apply a template the moment their café (and
first branch) exist.
"""
from decimal import Decimal

from apps.inventory.models import Ingredient, RecipeItem, StockItem
from apps.menu.models import Category, MenuItem

MENU_TEMPLATES = {
    "local_restaurant": {
        "label": "Local Restaurant",
        "description": "Everyday Ugandan meals: breakfast, lunch, and drinks.",
        "categories": {
            "Breakfast": [
                {
                    "name": "Rolex",
                    "selling_price": "3000",
                    "cost_price": "1200",
                    "recipe": [
                        {"ingredient": "Eggs", "unit": "piece", "quantity": "2"},
                        {"ingredient": "Chapati", "unit": "piece", "quantity": "1"},
                    ],
                },
                {
                    "name": "Tea",
                    "selling_price": "1500",
                    "cost_price": "500",
                    "recipe": [
                        {"ingredient": "Tea Leaves", "unit": "g", "quantity": "5"},
                        {"ingredient": "Milk", "unit": "ml", "quantity": "100"},
                    ],
                },
            ],
            "Lunch": [
                {
                    "name": "Rice & Beef Stew",
                    "selling_price": "8000",
                    "cost_price": "3500",
                    "recipe": [
                        {"ingredient": "Rice", "unit": "kg", "quantity": "0.3"},
                        {"ingredient": "Beef", "unit": "kg", "quantity": "0.2"},
                    ],
                },
                {
                    "name": "Matooke & Beans",
                    "selling_price": "6000",
                    "cost_price": "2500",
                    "recipe": [
                        {"ingredient": "Matooke", "unit": "kg", "quantity": "0.4"},
                        {"ingredient": "Beans", "unit": "kg", "quantity": "0.15"},
                    ],
                },
            ],
            "Drinks": [
                {
                    "name": "Soda",
                    "selling_price": "2000",
                    "cost_price": "1200",
                    "recipe": [{"ingredient": "Soda", "unit": "piece", "quantity": "1"}],
                },
                {
                    "name": "Bottled Water",
                    "selling_price": "1500",
                    "cost_price": "800",
                    "recipe": [{"ingredient": "Bottled Water", "unit": "piece", "quantity": "1"}],
                },
            ],
        },
    },
    "pork_joint": {
        "label": "Pork Joint",
        "description": "Roast pork, ribs, and the usual sides.",
        "categories": {
            "Pork": [
                {
                    "name": "Roast Pork (1kg)",
                    "selling_price": "25000",
                    "cost_price": "14000",
                    "recipe": [{"ingredient": "Pork", "unit": "kg", "quantity": "1"}],
                },
                {
                    "name": "Pork Ribs",
                    "selling_price": "15000",
                    "cost_price": "8000",
                    "recipe": [{"ingredient": "Pork Ribs", "unit": "kg", "quantity": "0.5"}],
                },
            ],
            "Sides": [
                {
                    "name": "Chips",
                    "selling_price": "4000",
                    "cost_price": "1500",
                    "recipe": [
                        {"ingredient": "Irish Potatoes", "unit": "kg", "quantity": "0.3"},
                        {"ingredient": "Cooking Oil", "unit": "ml", "quantity": "100"},
                    ],
                },
                {
                    "name": "Cassava",
                    "selling_price": "3000",
                    "cost_price": "1000",
                    "recipe": [{"ingredient": "Cassava", "unit": "kg", "quantity": "0.3"}],
                },
            ],
            "Drinks": [
                {
                    "name": "Soda",
                    "selling_price": "2000",
                    "cost_price": "1200",
                    "recipe": [{"ingredient": "Soda", "unit": "piece", "quantity": "1"}],
                },
            ],
        },
    },
    "cafe_coffee_shop": {
        "label": "Café & Coffee Shop",
        "description": "Coffee, tea, and light bakery items.",
        "categories": {
            "Coffee": [
                {
                    "name": "Espresso",
                    "selling_price": "3500",
                    "cost_price": "1000",
                    "recipe": [{"ingredient": "Coffee Beans", "unit": "g", "quantity": "18"}],
                },
                {
                    "name": "Cappuccino",
                    "selling_price": "4500",
                    "cost_price": "1500",
                    "recipe": [
                        {"ingredient": "Coffee Beans", "unit": "g", "quantity": "18"},
                        {"ingredient": "Milk", "unit": "ml", "quantity": "150"},
                    ],
                },
            ],
            "Bakery": [
                {
                    "name": "Cake Slice",
                    "selling_price": "5000",
                    "cost_price": "2000",
                    "recipe": [
                        {"ingredient": "Flour", "unit": "g", "quantity": "150"},
                        {"ingredient": "Sugar", "unit": "g", "quantity": "80"},
                    ],
                },
                {
                    "name": "Sandwich",
                    "selling_price": "6000",
                    "cost_price": "2500",
                    "recipe": [
                        {"ingredient": "Bread", "unit": "piece", "quantity": "2"},
                        {"ingredient": "Cheese", "unit": "g", "quantity": "30"},
                    ],
                },
            ],
        },
    },
    "fast_food": {
        "label": "Fast Food",
        "description": "Chips, chicken, burgers, and pizza.",
        "categories": {
            "Fast Foods": [
                {
                    "name": "Chips",
                    "selling_price": "4000",
                    "cost_price": "1500",
                    "recipe": [
                        {"ingredient": "Irish Potatoes", "unit": "kg", "quantity": "0.3"},
                        {"ingredient": "Cooking Oil", "unit": "ml", "quantity": "100"},
                    ],
                },
                {
                    "name": "Fried Chicken",
                    "selling_price": "9000",
                    "cost_price": "4500",
                    "recipe": [{"ingredient": "Chicken", "unit": "piece", "quantity": "1"}],
                },
                {
                    "name": "Burger",
                    "selling_price": "8000",
                    "cost_price": "4000",
                    "recipe": [
                        {"ingredient": "Beef", "unit": "kg", "quantity": "0.15"},
                        {"ingredient": "Bread", "unit": "piece", "quantity": "2"},
                    ],
                },
                {
                    "name": "Pizza (Small)",
                    "selling_price": "15000",
                    "cost_price": "7000",
                    "recipe": [
                        {"ingredient": "Flour", "unit": "g", "quantity": "250"},
                        {"ingredient": "Cheese", "unit": "g", "quantity": "150"},
                    ],
                },
            ],
        },
    },
    "bar_restaurant": {
        "label": "Bar & Restaurant",
        "description": "Grilled meats and drinks for an evening crowd.",
        "categories": {
            "Grills": [
                {
                    "name": "Grilled Chicken",
                    "selling_price": "12000",
                    "cost_price": "6000",
                    "recipe": [{"ingredient": "Chicken", "unit": "piece", "quantity": "1"}],
                },
                {
                    "name": "Goat Meat",
                    "selling_price": "14000",
                    "cost_price": "7500",
                    "recipe": [{"ingredient": "Goat Meat", "unit": "kg", "quantity": "0.4"}],
                },
            ],
            "Drinks": [
                {
                    "name": "Soda",
                    "selling_price": "2500",
                    "cost_price": "1200",
                    "recipe": [{"ingredient": "Soda", "unit": "piece", "quantity": "1"}],
                },
                {
                    "name": "Bottled Water",
                    "selling_price": "2000",
                    "cost_price": "800",
                    "recipe": [{"ingredient": "Bottled Water", "unit": "piece", "quantity": "1"}],
                },
            ],
        },
    },
    "juice_bar": {
        "label": "Juice Bar",
        "description": "Fresh juices, milkshakes, and smoothies.",
        "categories": {
            "Juices": [
                {
                    "name": "Passion Juice",
                    "selling_price": "4000",
                    "cost_price": "1500",
                    "recipe": [{"ingredient": "Passion Fruit", "unit": "kg", "quantity": "0.2"}],
                },
                {
                    "name": "Mango Juice",
                    "selling_price": "4000",
                    "cost_price": "1500",
                    "recipe": [{"ingredient": "Mango", "unit": "kg", "quantity": "0.25"}],
                },
                {
                    "name": "Milkshake",
                    "selling_price": "5000",
                    "cost_price": "2000",
                    "recipe": [
                        {"ingredient": "Milk", "unit": "ml", "quantity": "250"},
                        {"ingredient": "Sugar", "unit": "g", "quantity": "30"},
                    ],
                },
            ],
        },
    },
}


def apply_menu_template(template_key, tenant, branch=None):
    """Create this template's categories/menu items/recipes for `tenant`
    (and, if `branch` is given, register each ingredient as a trackable
    StockItem there at 0 on hand). Idempotent -- re-applying, or applying
    a second overlapping template, only fills in what's missing by name,
    matching the unique-name-per-café constraints already on Category/
    MenuItem/Ingredient rather than erroring or duplicating.
    """
    template = MENU_TEMPLATES[template_key]
    created = {"categories": 0, "menu_items": 0, "ingredients": 0, "stock_items": 0}

    for sort_order, (category_name, items) in enumerate(template["categories"].items()):
        category, category_created = Category.objects.get_or_create(
            tenant=tenant, name=category_name, defaults={"sort_order": sort_order}
        )
        if category_created:
            created["categories"] += 1

        for item_data in items:
            menu_item, item_created = MenuItem.objects.get_or_create(
                tenant=tenant,
                name=item_data["name"],
                defaults={
                    "category": category,
                    "selling_price": Decimal(item_data["selling_price"]),
                    "cost_price": Decimal(item_data["cost_price"]),
                },
            )
            if item_created:
                created["menu_items"] += 1

            for recipe_line in item_data.get("recipe", []):
                ingredient, ingredient_created = Ingredient.objects.get_or_create(
                    tenant=tenant,
                    name=recipe_line["ingredient"],
                    defaults={"unit": recipe_line["unit"]},
                )
                if ingredient_created:
                    created["ingredients"] += 1

                RecipeItem.objects.get_or_create(
                    menu_item=menu_item,
                    ingredient=ingredient,
                    defaults={"tenant": tenant, "quantity_required": Decimal(recipe_line["quantity"])},
                )

                if branch is not None:
                    _, stock_created = StockItem.objects.get_or_create(
                        tenant=tenant,
                        branch=branch,
                        ingredient=ingredient,
                        defaults={"quantity_on_hand": Decimal("0")},
                    )
                    if stock_created:
                        created["stock_items"] += 1

    return created
