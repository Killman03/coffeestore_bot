from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from typing import List
from datetime import date

from database.models import User, Product, SupplyStatus


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Get main menu keyboard."""
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📦 Товары"), KeyboardButton(text="📊 Склад"))
    builder.row(KeyboardButton(text="🚚 Заказы из Китая"), KeyboardButton(text="➕ Новый заказ"))
    builder.row(KeyboardButton(text="🔄 Обновить заказ"), KeyboardButton(text="🗑️ Удалить заказ"))
    builder.row(KeyboardButton(text="➕ Добавить товар"), KeyboardButton(text="💰 Продажа"))
    builder.row(KeyboardButton(text="📤 Экспорт Excel"), KeyboardButton(text="📋 Поступления по дате"))
    builder.row(KeyboardButton(text="📋 Продажи по дате"), KeyboardButton(text="⚙️ Настройки"))
    builder.row(KeyboardButton(text="ℹ️ Помощь"))
    return builder.as_markup(resize_keyboard=True)


def get_sellers_keyboard(sellers: List[User]) -> InlineKeyboardMarkup:
    """Get inline keyboard with sellers."""
    builder = InlineKeyboardBuilder()
    for seller in sellers:
        builder.button(
            text=seller.full_name,
            callback_data=f"seller_{seller.id}"
        )
    builder.adjust(2)
    return builder.as_markup()


def get_products_keyboard(products: List[Product], max_buttons: int = 50) -> InlineKeyboardMarkup:
    """Get inline keyboard with products.
    
    Args:
        products: List of products to show
        max_buttons: Maximum number of buttons to display (Telegram limit consideration)
    """
    builder = InlineKeyboardBuilder()
    for product in products[:max_buttons]:
        builder.button(
            text=f"{product.name}",
            callback_data=f"product_{product.id}"
        )
    builder.adjust(1)  # 1 button per row
    return builder.as_markup()


def get_edit_product_fields_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for selecting which product field to edit."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Название", callback_data="edit_name")
    builder.button(text="💱 Базовая цена (CNY)", callback_data="edit_base_price")
    builder.button(text="⚖️ Вес (кг)", callback_data="edit_weight")
    builder.button(text="🏷️ Цена продажи по умолчанию (сом)", callback_data="edit_default_sale")
    builder.button(text="🗒️ Описание", callback_data="edit_description")
    builder.adjust(1)
    return builder.as_markup()


def get_supply_status_keyboard() -> InlineKeyboardMarkup:
    """Get inline keyboard for supply status selection."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📦 Заказан", callback_data=f"status_{SupplyStatus.ORDERED.value}")
    builder.button(text="🚢 В пути", callback_data=f"status_{SupplyStatus.IN_TRANSIT.value}")
    builder.button(text="✅ Доставлен", callback_data=f"status_{SupplyStatus.DELIVERED.value}")
    builder.button(text="❌ Отменён", callback_data=f"status_{SupplyStatus.CANCELLED.value}")
    builder.adjust(2)
    return builder.as_markup()


def get_yes_no_keyboard() -> InlineKeyboardMarkup:
    """Get Yes/No inline keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да", callback_data="confirm_yes")
    builder.button(text="❌ Нет", callback_data="confirm_no")
    builder.adjust(2)
    return builder.as_markup()


def get_price_choice_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard to choose default sale price or custom."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ По умолчанию", callback_data="price_default")
    builder.button(text="✏️ Своя цена", callback_data="price_custom")
    builder.adjust(2)
    return builder.as_markup()


def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for settings menu."""
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 Продавцы", callback_data="settings_sellers")
    builder.button(text="💵 Финансы", callback_data="settings_finance")
    builder.adjust(2)
    return builder.as_markup()


def get_sellers_manage_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for sellers management."""
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить продавца", callback_data="seller_add")
    builder.adjust(1)
    return builder.as_markup()


def get_finance_settings_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for financial settings actions."""
    builder = InlineKeyboardBuilder()
    builder.button(text="💱 Изменить курс юаня", callback_data="finance_cny")
    builder.button(text="🚚 Изменить стоимость доставки", callback_data="finance_delivery")
    builder.adjust(1)
    return builder.as_markup()


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Get cancel keyboard."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="❌ Отмена")
    return builder.as_markup(resize_keyboard=True)


def get_cost_choice_keyboard() -> InlineKeyboardMarkup:
    """Get inline keyboard to choose default or custom cost parameters."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ По умолчанию", callback_data="item_cost_default")
    builder.button(text="✏️ Указать свои", callback_data="item_cost_custom")
    builder.adjust(2)
    return builder.as_markup()


def get_date_keyboard(dates: List[date]) -> InlineKeyboardMarkup:
    """Get inline keyboard with dates for selection. Shows only last 4 dates."""
    builder = InlineKeyboardBuilder()
    for d in dates[:4]:  # Limit to 4 dates
        builder.button(
            text=d.strftime("%d.%m.%Y"),
            callback_data=f"date_{d.isoformat()}"
        )
    builder.adjust(2)
    return builder.as_markup()


def get_supply_item_keyboard(item_id: int) -> InlineKeyboardMarkup:
    """Get inline keyboard for supply item actions."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить цену", callback_data=f"edit_supply_item_{item_id}")
    builder.button(text="🗑️ Удалить", callback_data=f"delete_supply_item_{item_id}")
    builder.adjust(1)
    return builder.as_markup()


def get_sale_keyboard(sale_id: int) -> InlineKeyboardMarkup:
    """Get inline keyboard for sale actions."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑️ Удалить", callback_data=f"delete_sale_{sale_id}")
    return builder.as_markup()


def get_warehouse_stock_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for warehouse actions: issue and seller balances."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📤 Выдать со склада", callback_data="warehouse_issue_start")
    builder.button(text="👥 Остатки у продавцов", callback_data="warehouse_seller_balances")
    builder.adjust(1)
    return builder.as_markup()


def get_quantity_quick_keyboard() -> InlineKeyboardMarkup:
    """Quick quantity buttons for warehouse issue."""
    builder = InlineKeyboardBuilder()
    for qty in (1, 2, 5, 10):
        builder.button(text=str(qty), callback_data=f"issue_qty_{qty}")
    builder.adjust(2)
    return builder.as_markup()

