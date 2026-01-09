from datetime import datetime, date
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.states import (
    NewSupplyStates,
    UpdateSupplyStates,
    ArrivalConfirmStates,
    ViewSupplyItemsStates,
    DeleteSupplyStates,
)
from bot.keyboards import (
    get_main_menu_keyboard,
    get_cancel_keyboard,
    get_supply_status_keyboard,
    get_products_keyboard,
    get_cost_choice_keyboard,
    get_date_keyboard,
    get_supply_item_keyboard,
    get_yes_no_keyboard,
)
from services.supply_service import SupplyService
from services.message_parser import parse_arrival_message
from services.product_service import ProductService
from database.models import User, SupplyStatus, SupplyOrderItem, SupplyOrder

router = Router()


@router.message(Command("new_supply"))
@router.message(F.text == "➕ Новый заказ")
async def cmd_new_supply(message: Message, state: FSMContext):
    """Start creating new supply order."""
    await state.set_state(NewSupplyStates.waiting_for_tracking)
    await state.update_data(items=[])
    await message.answer(
        "🚚 <b>Создание нового заказа из Китая</b>\n\n"
        "Введите трек-номер заказа:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(NewSupplyStates.waiting_for_tracking)
async def process_supply_tracking(message: Message, state: FSMContext, session: AsyncSession):
    """Process supply tracking number."""
    tracking = message.text.strip()
    
    # Check if tracking already exists
    existing = await SupplyService.get_supply_order_by_tracking(session, tracking)
    if existing:
        await message.answer(
            f"❌ Заказ с трек-номером <b>{tracking}</b> уже существует!",
            parse_mode="HTML"
        )
        return
    
    await state.update_data(tracking_number=tracking)
    await state.set_state(NewSupplyStates.waiting_for_date)
    await message.answer(
        f"✅ Трек-номер: <b>{tracking}</b>\n\n"
        "Введите дату заказа в формате ДД.ММ.ГГГГ\n"
        "Или отправьте 'сегодня' для текущей даты:",
        parse_mode="HTML"
    )


@router.message(NewSupplyStates.waiting_for_date)
async def process_supply_date(message: Message, state: FSMContext, session: AsyncSession):
    """Process supply order date."""
    try:
        if message.text.lower() in ["сегодня", "today"]:
            order_date = datetime.now()
        else:
            order_date = datetime.strptime(message.text.strip(), "%d.%m.%Y")
        
        await state.update_data(order_date=order_date)
        await state.set_state(NewSupplyStates.waiting_for_products)
        
        products = await ProductService.get_all_products(session)
        products_text = "\n".join([f"• {p.name}" for p in products[:30]])
        if len(products) > 30:
            products_text += f"\n... и ещё {len(products) - 30} товаров"
        
        await message.answer(
            f"✅ Дата заказа: <b>{order_date.strftime('%d.%m.%Y')}</b>\n\n"
            f"📦 Доступные товары:\n{products_text}\n\n"
            "Выберите товар кнопкой ниже или введите название товара для поиска:",
            parse_mode="HTML",
            reply_markup=get_products_keyboard(products)  # показываем все товары
        )
    except ValueError:
        await message.answer(
            "❌ Неверный формат даты!\n"
            "Используйте формат: ДД.ММ.ГГГГ (например, 15.10.2024)"
        )


@router.message(NewSupplyStates.waiting_for_products)
async def process_supply_product(message: Message, state: FSMContext, session: AsyncSession):
    """Process product ID for supply order."""
    if message.text.lower() in ["готово", "done", "завершить"]:
        data = await state.get_data()
        if not data.get("items"):
            await message.answer("❌ Добавьте хотя бы один товар в заказ!")
            return
        
        # Create supply order
        supply_order = await SupplyService.create_supply_order(
            session,
            tracking_number=data["tracking_number"],
            order_date=data["order_date"],
            items=data["items"],
        )
        
        await state.clear()
        
        items_text = "\n".join([
            f"  • {item.product.name}: {item.quantity} шт."
            for item in supply_order.items
        ])
        
        await message.answer(
            f"✅ <b>Заказ успешно создан!</b>\n\n"
            f"ID: <b>{supply_order.id}</b>\n"
            f"Трек-номер: <b>{supply_order.tracking_number}</b>\n"
            f"Дата: {supply_order.order_date.strftime('%d.%m.%Y')}\n"
            f"Статус: {supply_order.status.value}\n\n"
            f"Товары:\n{items_text}",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    text = message.text.strip()
    # Try numeric ID
    if text.isdigit():
        product = await ProductService.get_product_by_id(session, int(text))
        if not product:
            await message.answer("❌ Товар с таким ID не найден!")
            return
    else:
        # Try search by name
        products = await ProductService.search_products(session, text)
        if not products:
            # Show all active products to help user choose
            all_products = await ProductService.get_all_products(session)
            await message.answer(
                "❌ Товар не найден! Выберите из списка или введите точное название:",
                reply_markup=get_products_keyboard(all_products)
            )
            return
        if len(products) > 1:
            await message.answer(
                "Найдено несколько товаров. Выберите нужный из списка:",
                reply_markup=get_products_keyboard(products[:10])
            )
            return
        product = products[0]

    await state.update_data(current_product_id=product.id, current_product_name=product.name)
    await state.set_state(NewSupplyStates.waiting_for_quantity)
    await message.answer(
        f"✅ Товар: <b>{product.name}</b>\n\n"
        "Введите количество:",
        parse_mode="HTML"
    )


@router.callback_query(NewSupplyStates.waiting_for_products, F.data.startswith("product_"))
async def process_supply_product_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Handle product selection via inline button."""
    product_id = int(callback.data.split("_")[1])
    product = await ProductService.get_product_by_id(session, product_id)
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return

    await state.update_data(current_product_id=product.id, current_product_name=product.name)
    await state.set_state(NewSupplyStates.waiting_for_quantity)
    await callback.message.edit_text(
        f"✅ Товар: <b>{product.name}</b>\n\n"
        "Введите количество:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(NewSupplyStates.waiting_for_quantity)
async def process_supply_quantity(message: Message, state: FSMContext, session: AsyncSession):
    """Process product quantity for supply order, then ask for cost choice."""
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        data = await state.get_data()
        items = data.get("items", [])
        # Temporarily add item with no overrides yet; we'll update after cost choice
        items.append((data["current_product_id"], quantity))
        await state.update_data(items=items, current_quantity=quantity)
        await state.set_state(NewSupplyStates.waiting_for_cost_choice)
        # Load defaults to show in prompt
        from services.product_service import ProductService
        product = await ProductService.get_product_by_id(session, data["current_product_id"])
        defaults_text = (
            f"Использовать параметры по умолчанию (цена: {product.base_price_cny} CNY, "
            f"вес: {product.weight_kg} кг), или указать свои для этой поставки?"
        ) if product else "Использовать параметры по умолчанию, или указать свои для этой поставки?"
        await message.answer(defaults_text, reply_markup=get_cost_choice_keyboard())
    except ValueError:
        await message.answer("❌ Введите корректное положительное число!")


@router.callback_query(NewSupplyStates.waiting_for_cost_choice, F.data == "item_cost_default")
async def supply_cost_default(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """User chose default cost - finalize item and return to adding products."""
    # Finalize order immediately with current items
    data = await state.get_data()
    supply_order = await SupplyService.create_supply_order(
        session,
        tracking_number=data["tracking_number"],
        order_date=data["order_date"],
        items=data["items"],
    )
    await state.clear()
    await callback.message.edit_text(
        f"✅ Добавлено: <b>{data['current_product_name']}</b> - {data['current_quantity']} шт.",
        parse_mode="HTML"
    )
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(NewSupplyStates.waiting_for_cost_choice, F.data == "item_cost_custom")
async def supply_cost_custom(callback: CallbackQuery, state: FSMContext):
    """User chose custom cost - ask for price in CNY per unit."""
    await state.set_state(NewSupplyStates.waiting_for_custom_price)
    await callback.message.edit_text(
        "Введите цену за единицу в CNY (например: 16.96):"
    )
    await callback.answer()


@router.message(NewSupplyStates.waiting_for_custom_price)
async def process_custom_price(message: Message, state: FSMContext):
    from decimal import Decimal, InvalidOperation
    try:
        price = Decimal(message.text.replace(",", "."))
        if price <= 0:
            raise ValueError
        await state.update_data(custom_unit_price_cny=price)
        await state.set_state(NewSupplyStates.waiting_for_custom_weight)
        await message.answer("Введите вес за единицу (кг), например: 0.5")
    except (InvalidOperation, ValueError):
        await message.answer("❌ Введите корректное положительное число (например: 16.96)")


@router.message(NewSupplyStates.waiting_for_custom_weight)
async def process_custom_weight(message: Message, state: FSMContext, session: AsyncSession):
    from decimal import Decimal, InvalidOperation
    try:
        weight = Decimal(message.text.replace(",", "."))
        if weight <= 0:
            raise ValueError
        data = await state.get_data()
        # Store overrides for the last appended item
        # Create order immediately with current items
        supply_order = await SupplyService.create_supply_order(
            session,
            tracking_number=data["tracking_number"],
            order_date=data["order_date"],
            items=data["items"],
        )
        # Apply overrides to the matching item
        for item in supply_order.items:
            if item.product_id == data["current_product_id"]:
                item.unit_price_cny = data.get("custom_unit_price_cny")
                item.unit_weight_kg = weight
                break
        await session.commit()
        await state.clear()
        await message.answer(
            f"✅ Добавлено: <b>{data['current_product_name']}</b> - {data['current_quantity']} шт.\n"
            f"   Цена: {data.get('custom_unit_price_cny')} CNY, Вес: {weight} кг/шт.",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )
    except (InvalidOperation, ValueError):
        await message.answer("❌ Введите корректное положительное число (например: 0.5)")


@router.message(NewSupplyStates.waiting_for_quantity)
async def process_supply_quantity(message: Message, state: FSMContext):
    """Process product quantity for supply order."""
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        
        data = await state.get_data()
        items = data.get("items", [])
        items.append((data["current_product_id"], quantity))
        
        await state.update_data(items=items)
        await state.set_state(NewSupplyStates.waiting_for_products)
        
        await message.answer(
            f"✅ Добавлено: <b>{data['current_product_name']}</b> - {quantity} шт.\n\n"
            "Введите ID следующего товара или отправьте 'готово' для завершения:",
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer("❌ Введите корректное положительное число!")


@router.message(Command("supply_status"))
async def cmd_supply_status(message: Message, session: AsyncSession):
    """Show all supply orders with their status."""
    orders = await SupplyService.get_all_supply_orders(session)
    
    if not orders:
        await message.answer(
            "🚚 Нет заказов из Китая.\n"
            "Используйте /new_supply для создания."
        )
        return
    
    text = "🚚 <b>Заказы из Китая:</b>\n\n"
    
    status_emoji = {
        SupplyStatus.ORDERED: "📦",
        SupplyStatus.IN_TRANSIT: "🚢",
        SupplyStatus.DELIVERED: "✅",
        SupplyStatus.CANCELLED: "❌",
    }
    
    for order in orders:
        emoji = status_emoji.get(order.status, "❓")
        items_count = sum(item.quantity for item in order.items)
        # Determine product name(s) to show near tracking number
        product_names = [item.product.name for item in order.items if getattr(item, "product", None)]
        unique_names = list(dict.fromkeys(product_names))
        if unique_names:
            name_part = unique_names[0] if len(unique_names) == 1 else f"{unique_names[0]} и др."
        else:
            name_part = "-"
        
        text += (
            f"{emoji} <b>ID {order.id}:</b> {order.tracking_number} — {name_part}\n"
            f"   Дата: {order.order_date.strftime('%d.%m.%Y')}\n"
            f"   Статус: {order.status.value}\n"
            f"   Товаров: {items_count} шт.\n\n"
        )
    
    await message.answer(text, parse_mode="HTML")


@router.message(Command("update_supply"))
@router.message(F.text == "🔄 Обновить заказ")
async def cmd_update_supply(message: Message, state: FSMContext):
    """Start updating supply order status."""
    await state.set_state(UpdateSupplyStates.waiting_for_tracking)
    await message.answer(
        "🔄 <b>Обновление статуса заказа</b>\n\n"
        "Введите трек-номер или ID заказа:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(UpdateSupplyStates.waiting_for_tracking)
async def process_update_tracking(message: Message, state: FSMContext, session: AsyncSession):
    """Process tracking number or ID for status update."""
    text = message.text.strip()
    
    # Try to find by ID or tracking
    order = None
    # Prefer lookup by tracking first to avoid integer overflow on numeric trackings
    order = await SupplyService.get_supply_order_by_tracking(session, text)
    if not order and text.isdigit():
        try:
            candidate_id = int(text)
            # Guard against PostgreSQL INTEGER overflow
            if -2147483648 <= candidate_id <= 2147483647:
                order = await SupplyService.get_supply_order_by_id(session, candidate_id)
        except ValueError:
            order = None
    
    if not order:
        await message.answer("❌ Заказ не найден!")
        return
    
    await state.update_data(order_id=order.id)
    await state.set_state(UpdateSupplyStates.waiting_for_status)
    
    await message.answer(
        f"✅ Заказ найден:\n"
        f"ID: <b>{order.id}</b>\n"
        f"Трек-номер: <b>{order.tracking_number}</b>\n"
        f"Текущий статус: <b>{order.status.value}</b>\n\n"
        "Выберите новый статус:",
        parse_mode="HTML",
        reply_markup=get_supply_status_keyboard()
    )


@router.callback_query(UpdateSupplyStates.waiting_for_status, F.data.startswith("status_"))
async def process_update_status(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Process new status selection."""
    prefix = "status_"
    status_value = callback.data[len(prefix):] if callback.data.startswith(prefix) else callback.data
    status = SupplyStatus(status_value)
    
    data = await state.get_data()
    order = await SupplyService.update_supply_status(session, data["order_id"], status)
    
    await state.clear()
    
    await callback.message.edit_text(
        f"✅ <b>Статус заказа обновлён!</b>\n\n"
        f"ID: <b>{order.id}</b>\n"
        f"Трек-номер: <b>{order.tracking_number}</b>\n"
        f"Новый статус: <b>{order.status.value}</b>",
        parse_mode="HTML"
    )
    
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()


def _format_supply_order_delete_summary(order: SupplyOrder) -> str:
    """Build confirmation text for supply order deletion."""
    status_emoji = {
        SupplyStatus.ORDERED: "📦",
        SupplyStatus.IN_TRANSIT: "🚢",
        SupplyStatus.DELIVERED: "✅",
        SupplyStatus.CANCELLED: "❌",
    }
    status_names = {
        SupplyStatus.ORDERED: "Заказан",
        SupplyStatus.IN_TRANSIT: "В пути",
        SupplyStatus.DELIVERED: "Доставлен",
        SupplyStatus.CANCELLED: "Отменён",
    }
    emoji = status_emoji.get(order.status, "❓")
    status_text = status_names.get(order.status, order.status.value)
    order_date = order.order_date.strftime("%d.%m.%Y") if order.order_date else "-"
    delivery_line = ""
    if order.delivery_date:
        delivery_line = f"Дата доставки: {order.delivery_date.strftime('%d.%m.%Y')}\n"

    items = list(order.items or [])
    total_quantity = sum(int(item.quantity or 0) for item in items)
    item_lines: list[str] = []
    for item in items[:5]:
        product_name = item.product.name if getattr(item, "product", None) else f"ID {item.product_id}"
        item_lines.append(f"• {product_name}: {item.quantity} шт.")
    if len(items) > 5:
        item_lines.append(f"… и ещё {len(items) - 5} позиций")
    items_block = "\n".join(item_lines) if item_lines else "Нет позиций."

    return (
        "❗ <b>Подтвердите удаление заказа</b>\n\n"
        f"ID: <b>{order.id}</b>\n"
        f"Трек-номер: <b>{order.tracking_number}</b>\n"
        f"Статус: {emoji} {status_text}\n"
        f"Дата заказа: {order_date}\n"
        f"{delivery_line}"
        f"Позиций: {len(items)}\n"
        f"Общий объём: {total_quantity} шт.\n\n"
        f"{items_block}\n\n"
        "⚠️ При удалении будут очищены все складские остатки, связанные с этим заказом."
    )


@router.message(Command("delete_supply"))
@router.message(F.text == "🗑️ Удалить заказ")
async def cmd_delete_supply(message: Message, state: FSMContext):
    """Start supply order deletion flow."""
    await state.set_state(DeleteSupplyStates.waiting_for_identifier)
    await message.answer(
        "🗑️ <b>Удаление заказа</b>\n\n"
        "Введите трек-номер или ID заказа, который нужно удалить.\n"
        "❗ Все позиции поступления будут удалены, складские остатки пересчитаются.",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(DeleteSupplyStates.waiting_for_identifier)
async def process_delete_supply_identifier(message: Message, state: FSMContext, session: AsyncSession):
    """Process identifier for supply order deletion."""
    text = (message.text or "").strip()
    if text.lower() in ["отмена", "cancel", "❌ отмена"]:
        await state.clear()
        await message.answer("❌ Операция отменена.", reply_markup=get_main_menu_keyboard())
        return

    order = await SupplyService.get_supply_order_by_tracking(session, text)
    if not order and text.isdigit():
        try:
            candidate_id = int(text)
            if -2147483648 <= candidate_id <= 2147483647:
                order = await SupplyService.get_supply_order_by_id(session, candidate_id)
        except ValueError:
            order = None

    if not order:
        await message.answer("❌ Заказ не найден. Укажите корректный трек-номер или числовой ID.")
        return

    await state.update_data(
        delete_order_id=order.id,
        delete_order_tracking=order.tracking_number,
    )
    await state.set_state(DeleteSupplyStates.waiting_for_confirm)

    summary = _format_supply_order_delete_summary(order)
    await message.answer(summary, parse_mode="HTML", reply_markup=get_yes_no_keyboard())


@router.callback_query(DeleteSupplyStates.waiting_for_confirm)
async def process_delete_supply_confirm(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Handle confirmation for supply order deletion."""
    if callback.data == "confirm_no":
        await state.clear()
        await callback.message.edit_text("❌ Удаление заказа отменено.")
        await callback.message.answer("Выберите действие:", reply_markup=get_main_menu_keyboard())
        await callback.answer()
        return
    if callback.data != "confirm_yes":
        await callback.answer()
        return

    data = await state.get_data()
    order_id = data.get("delete_order_id")
    tracking = data.get("delete_order_tracking")

    success = await SupplyService.delete_supply_order(session, order_id)
    await state.clear()

    if success:
        text = (
            f"✅ Заказ <b>{tracking or order_id}</b> удалён.\n"
            "Связанные складские данные очищены."
        )
        await callback.answer("Заказ удалён")
    else:
        text = (
            f"❌ Не удалось удалить заказ (ID: {order_id}). Возможно, он уже удалён."
        )
        await callback.answer("Ошибка при удалении", show_alert=True)

    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.message.answer("Выберите действие:", reply_markup=get_main_menu_keyboard())


@router.message(F.text == "🚚 Заказы из Китая")
async def menu_supply(message: Message, session: AsyncSession):
    """Show supply menu."""
    # Show only orders that are currently in transit
    orders = await SupplyService.get_all_supply_orders(session)
    in_transit_orders = [o for o in orders if o.status == SupplyStatus.IN_TRANSIT]

    if not in_transit_orders:
        await message.answer("🚚 В пути заказов нет.")
        return

    text = "🚚 <b>В пути:</b>\n\n"

    status_emoji = {
        SupplyStatus.ORDERED: "📦",
        SupplyStatus.IN_TRANSIT: "🚢",
        SupplyStatus.DELIVERED: "✅",
        SupplyStatus.CANCELLED: "❌",
    }

    for order in in_transit_orders:
        emoji = status_emoji.get(order.status, "❓")
        items_count = sum(item.quantity for item in order.items)
        # Determine product name(s) to show near tracking number
        product_names = [item.product.name for item in order.items if getattr(item, "product", None)]
        unique_names = list(dict.fromkeys(product_names))
        if unique_names:
            name_part = unique_names[0] if len(unique_names) == 1 else f"{unique_names[0]} и др."
        else:
            name_part = "-"

        text += (
            f"{emoji} <b>ID {order.id}:</b> {order.tracking_number} — {name_part}\n"
            f"   Дата: {order.order_date.strftime('%d.%m.%Y')}\n"
            f"   Статус: {order.status.value}\n"
            f"   Товаров: {items_count} шт.\n\n"
        )

    await message.answer(text, parse_mode="HTML")


# Auto-parse arrival messages sent by admins and mark orders delivered
@router.message(F.text.startswith("📦 "))
async def auto_mark_delivered(message: Message, session: AsyncSession, state: FSMContext):
    """Parse delivery arrival message and ask for confirmation or manual input before updating."""

    tracking_numbers, total_weight, total_cost = parse_arrival_message(message.text)

    if not tracking_numbers:
        await message.answer("Не удалось найти трек-номера в сообщении. Проверьте формат.")
        return

    # Save parsed data into state for confirmation step
    await state.set_state(ArrivalConfirmStates.waiting_for_confirmation)
    await state.update_data(
        arrival_tracking_numbers=tracking_numbers,
        arrival_total_weight=str(total_weight) if total_weight is not None else None,
        arrival_total_cost=str(total_cost) if total_cost is not None else None,
    )

    # Build preview text
    preview_lines = [
        "Найдены следующие трек-номера:",
        *[f"📌 {t}" for t in tracking_numbers]
    ]
    if total_weight is not None:
        preview_lines.append(f"⚖️ Вес посылок ИТОГО: {total_weight} кг")
    if total_cost is not None:
        preview_lines.append(f"💰 Стоимость ИТОГО: {total_cost} с")
    preview_lines.append("")
    preview_lines.append("Обновить статус указанных заказов на Доставлено?")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="arrival_confirm")],
        [InlineKeyboardButton(text="✏️ Ввести вручную", callback_data="arrival_manual")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="arrival_cancel")],
    ])

    await message.answer("\n".join(preview_lines), reply_markup=kb)


@router.callback_query(ArrivalConfirmStates.waiting_for_confirmation, F.data == "arrival_cancel")
async def arrival_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Операция отменена.")
    await callback.answer()


@router.callback_query(ArrivalConfirmStates.waiting_for_confirmation, F.data == "arrival_manual")
async def arrival_manual(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ArrivalConfirmStates.waiting_for_manual_input)
    await callback.message.edit_text(
        "Отправьте трек-номера и (при необходимости) вес/стоимость в удобном формате.\n"
        "Пример:\n\n"
        "📌 SF3275881535019\n"
        "📌 464773038362140\n"
        "⚖️ Вес посылок ИТОГО: 0.666 кг\n"
        "💰 Стоимость ИТОГО: 149 с"
    )
    await callback.answer()


@router.message(ArrivalConfirmStates.waiting_for_manual_input)
async def arrival_manual_input(message: Message, state: FSMContext):
    tracking_numbers, total_weight, total_cost = parse_arrival_message(message.text)
    if not tracking_numbers:
        await message.answer("Не удалось распознать трек-номера. Отправьте данные ещё раз.")
        return

    await state.set_state(ArrivalConfirmStates.waiting_for_confirmation)
    await state.update_data(
        arrival_tracking_numbers=tracking_numbers,
        arrival_total_weight=str(total_weight) if total_weight is not None else None,
        arrival_total_cost=str(total_cost) if total_cost is not None else None,
    )

    preview_lines = [
        "Найдены следующие трек-номера:",
        *[f"📌 {t}" for t in tracking_numbers]
    ]
    if total_weight is not None:
        preview_lines.append(f"⚖️ Вес посылок ИТОГО: {total_weight} кг")
    if total_cost is not None:
        preview_lines.append(f"💰 Стоимость ИТОГО: {total_cost} с")
    preview_lines.append("")
    preview_lines.append("Обновить статус указанных заказов на Доставлено?")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="arrival_confirm")],
        [InlineKeyboardButton(text="✏️ Ввести вручную", callback_data="arrival_manual")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="arrival_cancel")],
    ])

    await message.answer("\n".join(preview_lines), reply_markup=kb)


@router.callback_query(ArrivalConfirmStates.waiting_for_confirmation, F.data == "arrival_confirm")
async def arrival_confirm(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    tracking_numbers = data.get("arrival_tracking_numbers", [])
    total_weight = data.get("arrival_total_weight")
    total_cost = data.get("arrival_total_cost")

    updated_orders = await SupplyService.mark_delivered_by_tracking(session, tracking_numbers)

    if not updated_orders:
        await callback.message.edit_text("По указанным трек-номерам заказы не найдены.")
        await state.clear()
        await callback.answer()
        return

    lines = ["✅ Обновлены статусы заказов на Доставлено:"]
    for order in updated_orders:
        items_count = sum(item.quantity for item in order.items)
        lines.append(f"ID {order.id}: {order.tracking_number} — {items_count} шт.")

    if total_weight:
        lines.append(f"⚖️ Вес ИТОГО: {total_weight} кг")
    if total_cost:
        lines.append(f"💰 Стоимость ИТОГО: {total_cost} с")

    await callback.message.edit_text("\n".join(lines))
    await state.clear()
    await callback.answer()


async def _show_supply_items(message_or_callback, items, selected_date: date, is_callback: bool = False):
    """Helper function to display supply items."""
    text = f"📋 <b>Поступления за {selected_date.strftime('%d.%m.%Y')}</b>\n\n"
    
    for idx, item in enumerate(items, 1):
        order = item.supply_order
        product = item.product
        price_info = f"{item.unit_price_cny} CNY" if item.unit_price_cny else f"{product.base_price_cny} CNY (по умолчанию)"
        weight_info = f"{item.unit_weight_kg} кг" if item.unit_weight_kg else f"{product.weight_kg} кг (по умолчанию)"
        
        text += (
            f"{idx}. <b>{product.name}</b>\n"
            f"   Количество: {item.quantity} шт.\n"
            f"   Цена: {price_info}\n"
            f"   Вес: {weight_info}\n"
            f"   Трек-номер: {order.tracking_number}\n\n"
        )
    
    # Send items in separate messages with delete buttons
    for item in items:
        product = item.product
        price_info = f"{item.unit_price_cny} CNY" if item.unit_price_cny else f"{product.base_price_cny} CNY (по умолчанию)"
        weight_info = f"{item.unit_weight_kg} кг" if item.unit_weight_kg else f"{product.weight_kg} кг (по умолчанию)"
        
        item_text = (
            f"📦 <b>{product.name}</b>\n"
            f"Количество: {item.quantity} шт.\n"
            f"Цена: {price_info}\n"
            f"Вес: {weight_info}\n"
            f"Трек-номер: {item.supply_order.tracking_number}\n"
            f"ID записи: {item.id}"
        )
        
        if is_callback:
            await message_or_callback.message.answer(
                item_text,
                parse_mode="HTML",
                reply_markup=get_supply_item_keyboard(item.id)
            )
        else:
            await message_or_callback.answer(
                item_text,
                parse_mode="HTML",
                reply_markup=get_supply_item_keyboard(item.id)
            )
    
    if is_callback:
        await message_or_callback.message.edit_text(text, parse_mode="HTML")
        await message_or_callback.answer()
    else:
        await message_or_callback.answer(text, parse_mode="HTML")


@router.message(Command("view_supplies"))
@router.message(F.text == "📋 Поступления по дате")
async def cmd_view_supplies(message: Message, state: FSMContext, session: AsyncSession):
    """Start viewing supply items by arrival date."""
    dates = await SupplyService.get_arrival_dates(session)
    
    if not dates:
        await message.answer(
            "📋 Нет записей о поступлениях.\n"
            "Сначала отметьте заказы как доставленные."
        )
        return
    
    await state.set_state(ViewSupplyItemsStates.waiting_for_date)
    recent_dates = dates[:4]  # Only last 4 dates
    
    text = (
        "📋 <b>Просмотр поступлений</b>\n\n"
        "Выберите дату прибытия из списка ниже или введите дату вручную в формате ДД.ММ.ГГГГ:"
    )
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_date_keyboard(recent_dates)
    )


@router.message(ViewSupplyItemsStates.waiting_for_date)
async def process_manual_arrival_date(message: Message, state: FSMContext, session: AsyncSession):
    """Process manually entered arrival date."""
    try:
        if message.text.lower() in ["отмена", "cancel", "❌ отмена"]:
            await state.clear()
            await message.answer("Операция отменена.", reply_markup=get_main_menu_keyboard())
            return
        
        # Try to parse date in DD.MM.YYYY format
        selected_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
        
        items = await SupplyService.get_items_by_arrival_date(session, selected_date)
        
        if not items:
            await message.answer(
                f"📋 На {selected_date.strftime('%d.%m.%Y')} записей о поступлениях нет."
            )
            return
        
        await state.update_data(arrival_date=selected_date.isoformat(), arrival_date_obj=selected_date)
        await state.set_state(ViewSupplyItemsStates.viewing_items)
        
        await _show_supply_items(message, items, selected_date, is_callback=False)
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат даты!\n"
            "Используйте формат: ДД.ММ.ГГГГ (например, 15.10.2024)\n"
            "Или выберите дату из списка выше."
        )


@router.callback_query(ViewSupplyItemsStates.waiting_for_date, F.data.startswith("date_"))
async def select_arrival_date(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Handle arrival date selection from inline keyboard."""
    date_str = callback.data.split("_", 1)[1]
    selected_date = date.fromisoformat(date_str)
    
    items = await SupplyService.get_items_by_arrival_date(session, selected_date)
    
    if not items:
        await callback.message.edit_text(
            f"📋 На {selected_date.strftime('%d.%m.%Y')} записей о поступлениях нет."
        )
        await state.clear()
        await callback.answer()
        return
    
    await state.update_data(arrival_date=date_str, arrival_date_obj=selected_date)
    await state.set_state(ViewSupplyItemsStates.viewing_items)
    
    await _show_supply_items(callback, items, selected_date, is_callback=True)


@router.callback_query(ViewSupplyItemsStates.viewing_items, F.data.startswith("edit_supply_item_"))
async def start_edit_supply_item(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Prompt user to enter a new unit price for supply item."""
    try:
        item_id = int(callback.data.split("_")[-1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка идентификатора записи", show_alert=True)
        return
    
    result = await session.execute(
        select(SupplyOrderItem)
        .options(
            selectinload(SupplyOrderItem.product),
            selectinload(SupplyOrderItem.supply_order),
        )
        .where(SupplyOrderItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    
    price_info = (
        f"{item.unit_price_cny} CNY" if item.unit_price_cny is not None
        else f"{item.product.base_price_cny} CNY (по умолчанию)"
    )
    
    await state.update_data(
        editing_item_id=item_id,
        editing_message_id=callback.message.message_id,
    )
    await state.set_state(ViewSupplyItemsStates.editing_price)
    
    await callback.message.answer(
        "✏️ Введите новую цену закупки для этой партии в CNY.\n"
        f"Текущая цена: {price_info}\n\n"
        "Отправьте 0, чтобы использовать цену по умолчанию из карточки товара.",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(ViewSupplyItemsStates.viewing_items, F.data.startswith("delete_supply_item_"))
async def delete_supply_item(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Handle supply item deletion."""
    item_id = int(callback.data.split("_")[-1])
    
    # Get item info before deletion
    result = await session.execute(
        select(SupplyOrderItem)
        .options(
            selectinload(SupplyOrderItem.product),
            selectinload(SupplyOrderItem.supply_order)
        )
        .where(SupplyOrderItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    
    if not item:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    
    product_name = item.product.name
    quantity = item.quantity
    
    # Delete the item
    success = await SupplyService.delete_supply_item(session, item_id)
    
    if success:
        await callback.message.edit_text(
            f"✅ <b>Запись удалена</b>\n\n"
            f"Товар: {product_name}\n"
            f"Количество: {quantity} шт.\n\n"
            f"<i>Записи о продажах этого товара не были удалены.</i>",
            parse_mode="HTML"
        )
        await callback.answer("Запись удалена")
    else:
        await callback.answer("Ошибка при удалении", show_alert=True)


@router.message(ViewSupplyItemsStates.editing_price)
async def process_edit_supply_item_price(message: Message, state: FSMContext, session: AsyncSession):
    """Process new unit price for supply item."""
    from decimal import Decimal, InvalidOperation
    
    text = (message.text or "").strip()
    if text.lower() in ["отмена", "cancel", "❌ отмена"]:
        await state.set_state(ViewSupplyItemsStates.viewing_items)
        await state.update_data(editing_item_id=None, editing_message_id=None)
        await message.answer("Операция отменена.", reply_markup=get_main_menu_keyboard())
        return
    
    try:
        value = Decimal(text.replace(",", "."))
    except (InvalidOperation, ValueError):
        await message.answer("❌ Введите корректное число (например: 16.95).")
        return
    
    if value < 0:
        await message.answer("❌ Цена не может быть отрицательной.")
        return
    
    data = await state.get_data()
    item_id = data.get("editing_item_id")
    if not item_id:
        await state.set_state(ViewSupplyItemsStates.viewing_items)
        await message.answer("❌ Не удалось определить запись. Выберите её заново.")
        return
    
    new_price = None if value == 0 else value
    updated_item = await SupplyService.update_supply_item(
        session,
        item_id=item_id,
        unit_price_cny=new_price,
    )
    if not updated_item:
        await state.set_state(ViewSupplyItemsStates.viewing_items)
        await message.answer("❌ Запись не найдена. Обновите список поступлений.")
        return
    
    price_info = (
        f"{updated_item.unit_price_cny} CNY"
        if updated_item.unit_price_cny is not None
        else f"{updated_item.product.base_price_cny} CNY (по умолчанию)"
    )
    weight_info = (
        f"{updated_item.unit_weight_kg} кг"
        if updated_item.unit_weight_kg is not None
        else f"{updated_item.product.weight_kg} кг (по умолчанию)"
    )
    
    editing_message_id = data.get("editing_message_id")
    if editing_message_id:
        try:
            await message.bot.edit_message_text(
                f"📦 <b>{updated_item.product.name}</b>\n"
                f"Количество: {updated_item.quantity} шт.\n"
                f"Цена: {price_info}\n"
                f"Вес: {weight_info}\n"
                f"Трек-номер: {updated_item.supply_order.tracking_number}\n"
                f"ID записи: {updated_item.id}",
                chat_id=message.chat.id,
                message_id=editing_message_id,
                parse_mode="HTML",
                reply_markup=get_supply_item_keyboard(updated_item.id),
            )
        except Exception:
            # Ignore message edit errors (e.g., message deleted)
            pass
    
    await message.answer(
        f"✅ Цена закупки обновлена: {price_info}",
        parse_mode="HTML"
    )
    
    await state.set_state(ViewSupplyItemsStates.viewing_items)
    await state.update_data(editing_item_id=None, editing_message_id=None)
