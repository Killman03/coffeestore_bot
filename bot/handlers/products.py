from decimal import Decimal, InvalidOperation
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states import AddProductStates, DeleteProductStates, EditProductStates
from bot.keyboards import get_main_menu_keyboard, get_cancel_keyboard, get_yes_no_keyboard, get_edit_product_fields_keyboard, get_products_keyboard
from services.product_service import ProductService
from database.models import User

router = Router()


@router.message(Command("add_product"))
@router.message(F.text == "➕ Добавить товар")
async def cmd_add_product(message: Message, state: FSMContext, user: User):
    """Start adding new product."""
    await state.set_state(AddProductStates.waiting_for_name)
    await message.answer(
        "📦 <b>Добавление нового товара</b>\n\n"
        "Введите название товара:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(AddProductStates.waiting_for_name)
async def process_product_name(message: Message, state: FSMContext):
    """Process product name."""
    await state.update_data(name=message.text)
    await state.set_state(AddProductStates.waiting_for_price)
    await message.answer(
        f"✅ Название: <b>{message.text}</b>\n\n"
        "Введите цену в юанях (CNY):",
        parse_mode="HTML"
    )


@router.message(AddProductStates.waiting_for_price)
async def process_product_price(message: Message, state: FSMContext):
    """Process product price."""
    try:
        price = Decimal(message.text.replace(",", "."))
        if price <= 0:
            raise ValueError("Price must be positive")
        
        await state.update_data(base_price_cny=price)
        await state.set_state(AddProductStates.waiting_for_weight)
        await message.answer(
            f"✅ Цена: <b>{price} CNY</b>\n\n"
            "Введите вес товара в килограммах (кг):",
            parse_mode="HTML"
        )
    except (InvalidOperation, ValueError):
        await message.answer(
            "❌ Ошибка! Введите корректное число больше нуля.\n"
            "Например: 16.96"
        )


@router.message(AddProductStates.waiting_for_weight)
async def process_product_weight(message: Message, state: FSMContext, session: AsyncSession):
    """Process product weight."""
    try:
        weight = Decimal(message.text.replace(",", "."))
        if weight <= 0:
            raise ValueError("Weight must be positive")
        
        await state.update_data(weight_kg=weight)
        # Ask for optional default sale price
        await message.answer(
            f"✅ Вес: <b>{weight} кг</b>\n\n"
            "Введите цену продажи по умолчанию (сом) или отправьте 0, чтобы пропустить:",
            parse_mode="HTML"
        )
        await state.set_state(AddProductStates.waiting_for_category)  # reuse next state slot
    except (InvalidOperation, ValueError):
        await message.answer(
            "❌ Ошибка! Введите корректное число больше нуля.\n"
            "Например: 0.5"
        )


@router.message(AddProductStates.waiting_for_category)
async def process_default_sale_price(message: Message, state: FSMContext, session: AsyncSession):
    """Capture optional default sale price and create product."""
    from decimal import Decimal, InvalidOperation
    try:
        value = Decimal(message.text.replace(",", "."))
        if value < 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        await message.answer("❌ Введите корректное неотрицательное число (например: 950)")
        return
    data = await state.get_data()
    product = await ProductService.create_product(
        session,
        name=data["name"],
        base_price_cny=data["base_price_cny"],
        weight_kg=data["weight_kg"],
        default_sale_price=(None if value == 0 else value),
    )
    await state.clear()
    await message.answer(
        f"✅ <b>Товар успешно добавлен!</b>\n\n"
        f"ID: <b>{product.id}</b>\n"
        f"Название: <b>{product.name}</b>\n"
        f"Цена: <b>{product.base_price_cny} CNY</b>\n"
        f"Вес: <b>{product.weight_kg} кг</b>\n"
        f"Цена продажи по умолчанию: <b>{product.default_sale_price or '—'}</b>",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard()
    )


@router.message(Command("products"))
@router.message(F.text == "📦 Товары")
async def cmd_products(message: Message, session: AsyncSession):
    """Show all products."""
    products = await ProductService.get_all_products(session)
    
    if not products:
        await message.answer(
            "📦 Список товаров пуст.\n"
            "Используйте /add_product для добавления."
        )
        return
    
    text = "📦 <b>Список товаров:</b>\n\n"
    for product in products:
        text += (
            f"🔹 <b>ID {product.id}:</b> {product.name}\n"
            f"   Цена: {product.base_price_cny} CNY\n"
            f"   Вес: {product.weight_kg} кг\n\n"
        )
    
    await message.answer(text, parse_mode="HTML")


@router.message(Command("edit_product"))
async def cmd_edit_product(message: Message, state: FSMContext):
    await state.set_state(EditProductStates.waiting_for_product)
    await message.answer("✏️ Введите ID или название товара для редактирования:", reply_markup=get_cancel_keyboard())


@router.message(EditProductStates.waiting_for_product)
async def process_edit_select_product(message: Message, state: FSMContext, session: AsyncSession):
    text = message.text.strip()
    product = None
    if text.isdigit():
        product = await ProductService.get_product_by_id(session, int(text))
    else:
        matches = await ProductService.search_products(session, text)
        if len(matches) == 1:
            product = matches[0]
        elif len(matches) > 1:
            await message.answer("Найдено несколько товаров. Выберите из списка:", reply_markup=get_products_keyboard(matches[:10]))
            return
    if not product:
        await message.answer("❌ Товар не найден. Укажите точный ID или уникальное название.")
        return
    await state.update_data(edit_product_id=product.id)
    await state.set_state(EditProductStates.waiting_for_field)
    await message.answer(
        f"Редактируем: <b>{product.name}</b> (ID: {product.id})\nВыберите поле для изменения:",
        parse_mode="HTML",
        reply_markup=get_edit_product_fields_keyboard()
    )


@router.callback_query(EditProductStates.waiting_for_field)
async def process_edit_choose_field(callback: CallbackQuery, state: FSMContext):
    mapping = {
        "edit_name": "name",
        "edit_base_price": "base_price_cny",
        "edit_weight": "weight_kg",
        "edit_default_sale": "default_sale_price",
        "edit_description": "description",
    }
    field = mapping.get(callback.data)
    if not field:
        await callback.answer()
        return
    await state.update_data(edit_field=field)
    await state.set_state(EditProductStates.waiting_for_value)
    prompts = {
        "name": "Введите новое название:",
        "base_price_cny": "Введите новую базовую цену (CNY):",
        "weight_kg": "Введите новый вес (кг):",
        "default_sale_price": "Введите новую цену продажи по умолчанию (сом) или 0, чтобы очистить:",
        "description": "Введите новое описание (можно оставить пустым):",
    }
    await callback.message.edit_text(prompts[field])
    await callback.answer()


@router.message(EditProductStates.waiting_for_value)
async def process_edit_value(message: Message, state: FSMContext, session: AsyncSession):
    from decimal import Decimal, InvalidOperation
    data = await state.get_data()
    field = data.get("edit_field")
    product_id = data.get("edit_product_id")
    kwargs = {}
    try:
        if field == "name":
            kwargs["name"] = message.text.strip()
        elif field == "base_price_cny":
            val = Decimal(message.text.replace(",", "."))
            if val <= 0:
                raise ValueError
            kwargs["base_price_cny"] = val
        elif field == "weight_kg":
            val = Decimal(message.text.replace(",", "."))
            if val <= 0:
                raise ValueError
            kwargs["weight_kg"] = val
        elif field == "default_sale_price":
            val = Decimal(message.text.replace(",", "."))
            if val < 0:
                raise ValueError
            kwargs["default_sale_price"] = None if val == 0 else val
        elif field == "description":
            kwargs["description"] = message.text.strip() or None
        else:
            await message.answer("❌ Неизвестное поле")
            return
    except (InvalidOperation, ValueError):
        await message.answer("❌ Неверное значение. Попробуйте ещё раз.")
        return

    updated = await ProductService.update_product(session, product_id, **kwargs)
    await state.clear()
    if updated:
        await message.answer(
            "✅ Товар обновлён.",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await message.answer("❌ Не удалось обновить товар.")


@router.message(Command("delete_product"))
async def cmd_delete_product(message: Message, state: FSMContext):
    """Start product deactivation flow."""
    await state.set_state(DeleteProductStates.waiting_for_product)
    await message.answer(
        "🗑️ Введите ID товара или название для деактивации:",
        reply_markup=get_cancel_keyboard()
    )


@router.message(DeleteProductStates.waiting_for_product)
async def process_delete_product_select(message: Message, state: FSMContext, session: AsyncSession):
    text = message.text.strip()
    product = None
    if text.isdigit():
        product = await ProductService.get_product_by_id(session, int(text))
    else:
        from services.product_service import ProductService as PS
        matches = await PS.search_products(session, text)
        if len(matches) == 1:
            product = matches[0]
    if not product:
        await message.answer("❌ Товар не найден. Укажите точный ID или уникальное название.")
        return
    
    # Check if product is already deactivated
    if not product.is_active:
        await message.answer(
            f"ℹ️ Товар <b>{product.name}</b> (ID: {product.id}) уже деактивирован.",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )
        await state.clear()
        return
    
    await state.update_data(delete_product_id=product.id, delete_product_name=product.name)
    await state.set_state(DeleteProductStates.waiting_for_confirm)
    
    await message.answer(
        f"❗ Подтвердите деактивацию товара: <b>{product.name}</b> (ID: {product.id}).\n\n"
        f"Товар будет скрыт из списков, но все данные (продажи, остатки) сохранятся.",
        parse_mode="HTML",
        reply_markup=get_yes_no_keyboard()
    )


@router.callback_query(DeleteProductStates.waiting_for_confirm)
async def process_delete_product_confirm(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    if callback.data == "confirm_no":
        await state.clear()
        await callback.message.edit_text("❌ Деактивация отменена.")
        await callback.answer()
        return
    if callback.data != "confirm_yes":
        await callback.answer()
        return
    data = await state.get_data()
    
    # Use deactivation instead of deletion
    ok = await ProductService.deactivate_product(session, data["delete_product_id"])
    await state.clear()
    if ok:
        await callback.message.edit_text(
            f"✅ Товар деактивирован: <b>{data['delete_product_name']}</b>.\n\n"
            f"Товар скрыт из списков, но все данные сохранены.",
            parse_mode="HTML"
        )
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await callback.message.edit_text("❌ Не удалось деактивировать товар — возможно, он уже удалён.")
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=get_main_menu_keyboard()
        )
    await callback.answer()


@router.message(Command("stock"))
@router.message(F.text == "📊 Склад")
async def cmd_stock(message: Message, session: AsyncSession):
    """Show stock levels."""
    products_with_stock = await ProductService.get_products_with_stock_summary(session)
    
    if not products_with_stock:
        await message.answer(
            "📊 Склад пуст.\n"
            "Используйте /new_supply для создания заказа."
        )
        return
    
    text = "📊 <b>Остатки на складе:</b>\n\n"
    total_items = 0
    total_stock_value = Decimal("0")

    def format_currency(value: Decimal) -> str:
        return f"{value:,.2f}".replace(",", " ")
    
    for product, stock, stock_value in products_with_stock:
        stock_emoji = "✅" if stock > 10 else "⚠️" if stock > 0 else "❌"
        lines = [
            f"{stock_emoji} <b>{product.name}</b>",
            f"   ID: {product.id} | Остаток: <b>{stock} шт.</b>",
        ]
        if stock > 0:
            lines.append(f"   Себестоимость на складе: <b>{format_currency(stock_value)}</b> сом")

        text += "\n".join(lines) + "\n\n"
        total_items += stock
        total_stock_value += stock_value
    
    text += (
        f"📦 <b>Всего товаров:</b> {total_items} шт.\n"
        f"💰 <b>Стоимость склада:</b> {format_currency(total_stock_value)} сом"
    )
    
    await message.answer(text, parse_mode="HTML")

