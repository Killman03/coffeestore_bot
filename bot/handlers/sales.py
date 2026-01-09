from decimal import Decimal, InvalidOperation
from datetime import datetime, date
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.states import SaleStates, ViewSalesStates
from bot.keyboards import (
    get_main_menu_keyboard,
    get_cancel_keyboard,
    get_sellers_keyboard,
    get_price_choice_keyboard,
    get_date_keyboard,
    get_sale_keyboard,
)
from services.sale_service import SaleService
from services.product_service import ProductService
from services.user_service import UserService
from database.models import User, Sale

router = Router()


@router.message(Command("sale"))
@router.message(F.text == "💰 Продажа")
async def cmd_sale(message: Message, state: FSMContext):
    """Start registering a sale."""
    await state.set_state(SaleStates.waiting_for_product)
    await message.answer(
        "💰 <b>Регистрация продажи</b>\n\n"
        "Введите ID товара или название для поиска:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(SaleStates.waiting_for_product)
async def process_sale_product(message: Message, state: FSMContext, session: AsyncSession):
    """Process product selection for sale."""
    text = message.text.strip()
    
    # Try to find by ID first
    product = None
    if text.isdigit():
        product = await ProductService.get_product_by_id(session, int(text))
    
    # If not found, search by name
    if not product:
        products = await ProductService.search_products(session, text)
        if not products:
            await message.answer(
                "❌ Товар не найден!\n"
                "Попробуйте другой ID или название."
            )
            return
        elif len(products) > 1:
            products_text = "\n".join([f"ID {p.id}: {p.name}" for p in products[:10]])
            await message.answer(
                f"Найдено несколько товаров:\n{products_text}\n\n"
                "Уточните ID товара:"
            )
            return
        else:
            product = products[0]
    
    # Check stock
    stock = await ProductService.get_product_stock(session, product.id)
    if stock <= 0:
        await message.answer(
            f"⚠️ Товар <b>{product.name}</b> отсутствует на складе!\n"
            f"Текущий остаток: {stock} шт.",
            parse_mode="HTML"
        )
        await state.clear()
        return
    
    await state.update_data(product_id=product.id, product_name=product.name, available_stock=stock)
    # If default sale price exists, offer to use it
    if getattr(product, "default_sale_price", None):
        await state.set_state(SaleStates.waiting_for_price_choice)
        await message.answer(
            f"✅ Товар: <b>{product.name}</b>\n"
            f"Остаток: <b>{stock} шт.</b>\n"
            f"Цена по умолчанию: <b>{product.default_sale_price}</b> сом\n\n"
            "Использовать её или указать свою?",
            parse_mode="HTML",
            reply_markup=get_price_choice_keyboard()
        )
    else:
        await state.set_state(SaleStates.waiting_for_price)
        await message.answer(
            f"✅ Товар: <b>{product.name}</b>\n"
            f"Остаток: <b>{stock} шт.</b>\n\n"
            "Введите цену продажи в сомах:",
            parse_mode="HTML"
        )


@router.callback_query(SaleStates.waiting_for_price_choice)
async def price_choice(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    product = await ProductService.get_product_by_id(session, data["product_id"])
    if callback.data == "price_default" and product and product.default_sale_price:
        await state.update_data(sale_price=product.default_sale_price)
        await state.set_state(SaleStates.waiting_for_quantity)
        await callback.message.edit_text(
            f"✅ Цена: <b>{product.default_sale_price} сом</b>\n\n"
            f"Доступно: {data['available_stock']} шт.\n"
            "Введите количество:",
            parse_mode="HTML"
        )
        await callback.answer()
        return
    # Else ask custom
    await state.set_state(SaleStates.waiting_for_price)
    await callback.message.edit_text(
        "Введите цену продажи в сомах:",
        parse_mode="HTML"
    )
    await callback.answer()


def _parse_quick_sale(text: str):
    """Parse 'name qty price' from free text. Returns (name, qty:int, price:Decimal) or (None,...)."""
    from decimal import Decimal, InvalidOperation
    parts = text.strip().split()
    if len(parts) < 3:
        return None, None, None
    # Assume last two tokens are qty and price
    try:
        qty = int(parts[-2])
        if qty <= 0:
            return None, None, None
    except ValueError:
        return None, None, None
    try:
        price = Decimal(parts[-1].replace(",", "."))
        if price <= 0:
            return None, None, None
    except (InvalidOperation, ValueError):
        return None, None, None
    name = " ".join(parts[:-2]).strip()
    if not name:
        return None, None, None
    return name, qty, price


@router.message(F.text.regexp(r"^.+\s+\d+\s+\d+(?:[\.,]\d+)?$"))
async def quick_add_sale(message: Message, session: AsyncSession, user: User, state: FSMContext):
    """Quick sale: free-text 'ProductName qty price'. Skips if text doesn't match."""
    # Do not intercept messages when user is in any FSM flow (e.g., finance settings input)
    current_state = await state.get_state()
    if current_state:
        return
    if not message.text:
        return
    name, qty, price = _parse_quick_sale(message.text)
    if not all([name, qty, price]):
        return  # not our format; let other handlers process

    # Find product by name
    products = await ProductService.search_products(session, name)
    if not products:
        await message.answer(
            "❌ Товар не найден. Уточните название или введите ID товара." 
        )
        return
    if len(products) > 1:
        options = "\n".join([f"ID {p.id}: {p.name}" for p in products[:10]])
        await message.answer(
            f"Найдено несколько товаров:\n{options}\n\nОтправьте точный ID и повторите ввод (Напр.: Питчер 2 1000)."
        )
        return
    product = products[0]

    # Check stock
    stock = await ProductService.get_product_stock(session, product.id)
    if qty > stock:
        await message.answer(
            f"❌ Недостаточно товара на складе. Доступно: {stock} шт."
        )
        return

    # Determine seller from Telegram user
    seller_id = user.id if user else None
    if not seller_id:
        # Fallback: get or create by telegram id
        tg = message.from_user
        u = await UserService.get_or_create_user(
            session,
            telegram_id=tg.id,
            username=tg.username,
            first_name=tg.first_name,
            last_name=tg.last_name,
        )
        seller_id = u.id

    sales = await SaleService.create_sale(
        session,
        product_id=product.id,
        seller_id=seller_id,
        quantity=qty,
        sale_price=price,
        sale_date=datetime.now(),
    )
    if not sales:
        await message.answer("❌ Не удалось создать продажу. Проверьте настройки финансов.")
        return

    total_quantity = sum(s.quantity for s in sales)
    total_revenue = price * total_quantity
    total_cost = sum(s.cost_price * s.quantity for s in sales)
    total_profit = sum(s.profit for s in sales)

    breakdown_lines = "\n".join(
        f"• {s.quantity} шт. по себестоимости {s.cost_price:.2f} сом → прибыль {s.profit:.2f} сом"
        for s in sales
    )

    await message.answer(
        f"✅ Продажа добавлена!\n\n"
        f"Товар: <b>{product.name}</b>\n"
        f"Цена: {price} сом/шт.\n"
        f"Количество: {total_quantity} шт.\n"
        f"Продавец: <b>{sales[0].seller.full_name}</b>\n\n"
        f"💰 Выручка: {total_revenue} сом\n"
        f"💵 Себестоимость: {total_cost:.2f} сом\n"
        f"📈 Прибыль: <b>{total_profit:.2f} сом</b>\n"
        + (f"\n🔹 Разбивка:\n{breakdown_lines}" if len(sales) > 1 else ""),
        parse_mode="HTML"
    )
@router.message(SaleStates.waiting_for_price)
async def process_sale_price(message: Message, state: FSMContext):
    """Process sale price."""
    try:
        price = Decimal(message.text.replace(",", "."))
        if price <= 0:
            raise ValueError("Price must be positive")
        
        await state.update_data(sale_price=price)
        await state.set_state(SaleStates.waiting_for_quantity)
        
        data = await state.get_data()
        await message.answer(
            f"✅ Цена: <b>{price} сом</b>\n\n"
            f"Доступно: {data['available_stock']} шт.\n"
            "Введите количество:",
            parse_mode="HTML"
        )
    except (InvalidOperation, ValueError):
        await message.answer(
            "❌ Ошибка! Введите корректное число больше нуля.\n"
            "Например: 900"
        )


@router.message(SaleStates.waiting_for_quantity)
async def process_sale_quantity(message: Message, state: FSMContext, session: AsyncSession):
    """Process sale quantity."""
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        
        data = await state.get_data()
        if quantity > data["available_stock"]:
            await message.answer(
                f"❌ Недостаточно товара на складе!\n"
                f"Доступно: {data['available_stock']} шт."
            )
            return
        
        await state.update_data(quantity=quantity)
        await state.set_state(SaleStates.waiting_for_seller)
        
        # Get all sellers
        sellers = await UserService.get_all_active_sellers(session)
        
        await message.answer(
            f"✅ Количество: <b>{quantity} шт.</b>\n\n"
            "Выберите продавца:",
            parse_mode="HTML",
            reply_markup=get_sellers_keyboard(sellers)
        )
    except ValueError:
        await message.answer("❌ Введите корректное положительное целое число!")


@router.callback_query(SaleStates.waiting_for_seller, F.data.startswith("seller_"))
async def process_sale_seller(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Process seller selection."""
    seller_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    
    # Create sale
    sales = await SaleService.create_sale(
        session,
        product_id=data["product_id"],
        seller_id=seller_id,
        quantity=data["quantity"],
        sale_price=data["sale_price"],
        sale_date=datetime.now(),
    )
    
    if not sales:
        await callback.message.edit_text(
            "❌ Ошибка при создании продажи!\n"
            "Проверьте настройки финансов."
        )
        await state.clear()
        await callback.answer()
        return
    
    await state.clear()
    
    total_quantity = sum(s.quantity for s in sales)
    total_revenue = data["sale_price"] * total_quantity
    total_cost = sum(s.cost_price * s.quantity for s in sales)
    total_profit = sum(s.profit for s in sales)

    breakdown_lines = "\n".join(
        f"• {s.quantity} шт. по себестоимости {s.cost_price:.2f} сом → прибыль {s.profit:.2f} сом"
        for s in sales
    )
    
    await callback.message.edit_text(
        f"✅ <b>Продажа зарегистрирована!</b>\n\n"
        f"Товар: <b>{data['product_name']}</b>\n"
        f"Цена: {data['sale_price']} сом/шт.\n"
        f"Количество: {total_quantity} шт.\n"
        f"Продавец: <b>{sales[0].seller.full_name}</b>\n\n"
        f"💰 Выручка: {total_revenue} сом\n"
        f"💵 Себестоимость: {total_cost:.2f} сом\n"
        f"📈 Прибыль: <b>{total_profit:.2f} сом</b>"
        + (f"\n\n🔹 Разбивка:\n{breakdown_lines}" if len(sales) > 1 else ""),
        parse_mode="HTML"
    )
    
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()


@router.message(Command("today_sales"))
async def cmd_today_sales(message: Message, session: AsyncSession):
    """Show today's sales."""
    sales = await SaleService.get_today_sales(session)
    
    if not sales:
        await message.answer(
            "💰 Сегодня продаж пока не было.\n"
            "Используйте /sale для регистрации продажи."
        )
        return
    
    text = f"💰 <b>Продажи за сегодня ({date.today().strftime('%d.%m.%Y')}):</b>\n\n"
    
    total_revenue = Decimal(0)
    total_profit = Decimal(0)
    total_quantity = 0
    
    for sale in sales:
        revenue = sale.sale_price * sale.quantity
        text += (
            f"🔹 <b>{sale.product.name}</b>\n"
            f"   Цена: {sale.sale_price} сом × {sale.quantity} шт. = {revenue} сом\n"
            f"   Прибыль: {sale.profit:.2f} сом\n"
            f"   Продавец: {sale.seller.full_name}\n"
            f"   Время: {sale.sale_date.strftime('%H:%M')}\n\n"
        )
        total_revenue += revenue
        total_profit += sale.profit
        total_quantity += sale.quantity
    
    text += (
        f"📊 <b>Итого:</b>\n"
        f"Продано: {total_quantity} шт.\n"
        f"Выручка: {total_revenue} сом\n"
        f"Прибыль: <b>{total_profit:.2f} сом</b>"
    )
    
    await message.answer(text, parse_mode="HTML")


@router.message(Command("month_sales"))
async def cmd_month_sales(message: Message, session: AsyncSession):
    """Show current month sales."""
    sales = await SaleService.get_current_month_sales(session)
    
    today = date.today()
    month_name = today.strftime("%B %Y")
    
    if not sales:
        await message.answer(
            f"💰 В {month_name} продаж пока не было.\n"
            "Используйте /sale для регистрации продажи."
        )
        return
    
    total_revenue = sum(sale.sale_price * sale.quantity for sale in sales)
    total_profit = sum(sale.profit for sale in sales)
    total_quantity = sum(sale.quantity for sale in sales)
    
    # Group by product
    products_stats = {}
    for sale in sales:
        if sale.product_id not in products_stats:
            products_stats[sale.product_id] = {
                'name': sale.product.name,
                'quantity': 0,
                'revenue': Decimal(0),
                'profit': Decimal(0),
            }
        products_stats[sale.product_id]['quantity'] += sale.quantity
        products_stats[sale.product_id]['revenue'] += sale.sale_price * sale.quantity
        products_stats[sale.product_id]['profit'] += sale.profit
    
    text = f"💰 <b>Продажи за {month_name}:</b>\n\n"
    
    for stats in sorted(products_stats.values(), key=lambda x: x['profit'], reverse=True)[:10]:
        text += (
            f"🔹 <b>{stats['name']}</b>\n"
            f"   Продано: {stats['quantity']} шт.\n"
            f"   Выручка: {stats['revenue']} сом\n"
            f"   Прибыль: {stats['profit']:.2f} сом\n\n"
        )
    
    text += (
        f"📊 <b>Итого:</b>\n"
        f"Продаж: {len(sales)} шт.\n"
        f"Товаров: {total_quantity} шт.\n"
        f"Выручка: {total_revenue} сом\n"
        f"Прибыль: <b>{total_profit:.2f} сом</b>"
    )
    
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "💰 Продажи")
async def menu_sales(message: Message, session: AsyncSession):
    """Show sales menu."""
    await cmd_today_sales(message, session)


async def _show_sales(message_or_callback, sales, selected_date: date, is_callback: bool = False):
    """Helper function to display sales."""
    text = f"📋 <b>Продажи за {selected_date.strftime('%d.%m.%Y')}</b>\n\n"
    
    total_revenue = Decimal(0)
    total_profit = Decimal(0)
    total_quantity = 0
    
    for idx, sale in enumerate(sales, 1):
        revenue = sale.sale_price * sale.quantity
        total_revenue += revenue
        total_profit += sale.profit
        total_quantity += sale.quantity
        
        text += (
            f"{idx}. <b>{sale.product.name}</b>\n"
            f"   Количество: {sale.quantity} шт.\n"
            f"   Цена: {sale.sale_price} сом/шт.\n"
            f"   Выручка: {revenue} сом\n"
            f"   Прибыль: {sale.profit:.2f} сом\n"
            f"   Продавец: {sale.seller.full_name}\n"
            f"   Время: {sale.sale_date.strftime('%H:%M')}\n\n"
        )
    
    text += (
        f"📊 <b>Итого:</b>\n"
        f"Продано: {total_quantity} шт.\n"
        f"Выручка: {total_revenue} сом\n"
        f"Прибыль: {total_profit:.2f} сом"
    )
    
    # Send sales in separate messages with delete buttons
    for sale in sales:
        revenue = sale.sale_price * sale.quantity
        sale_text = (
            f"💰 <b>{sale.product.name}</b>\n"
            f"Количество: {sale.quantity} шт.\n"
            f"Цена: {sale.sale_price} сом/шт.\n"
            f"Выручка: {revenue} сом\n"
            f"Прибыль: {sale.profit:.2f} сом\n"
            f"Продавец: {sale.seller.full_name}\n"
            f"Время: {sale.sale_date.strftime('%H:%M')}\n"
            f"ID продажи: {sale.id}"
        )
        
        if is_callback:
            await message_or_callback.message.answer(
                sale_text,
                parse_mode="HTML",
                reply_markup=get_sale_keyboard(sale.id)
            )
        else:
            await message_or_callback.answer(
                sale_text,
                parse_mode="HTML",
                reply_markup=get_sale_keyboard(sale.id)
            )
    
    if is_callback:
        await message_or_callback.message.edit_text(text, parse_mode="HTML")
        await message_or_callback.answer()
    else:
        await message_or_callback.answer(text, parse_mode="HTML")


@router.message(Command("view_sales"))
@router.message(F.text == "📋 Продажи по дате")
async def cmd_view_sales(message: Message, state: FSMContext, session: AsyncSession):
    """Start viewing sales by date."""
    dates = await SaleService.get_sale_dates(session)
    
    if not dates:
        await message.answer(
            "📋 Нет записей о продажах.\n"
            "Используйте /sale для регистрации продажи."
        )
        return
    
    await state.set_state(ViewSalesStates.waiting_for_date)
    recent_dates = dates[:4]  # Only last 4 dates
    
    text = (
        "📋 <b>Просмотр продаж</b>\n\n"
        "Выберите дату из списка ниже или введите дату вручную в формате ДД.ММ.ГГГГ:"
    )
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_date_keyboard(recent_dates)
    )


@router.message(ViewSalesStates.waiting_for_date)
async def process_manual_sale_date(message: Message, state: FSMContext, session: AsyncSession):
    """Process manually entered sale date."""
    try:
        if message.text.lower() in ["отмена", "cancel", "❌ отмена"]:
            await state.clear()
            await message.answer("Операция отменена.", reply_markup=get_main_menu_keyboard())
            return
        
        # Try to parse date in DD.MM.YYYY format
        selected_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
        
        sales = await SaleService.get_sales_by_date(session, selected_date)
        
        if not sales:
            await message.answer(
                f"📋 На {selected_date.strftime('%d.%m.%Y')} продаж не было."
            )
            return
        
        await state.update_data(sale_date=selected_date.isoformat(), sale_date_obj=selected_date)
        await state.set_state(ViewSalesStates.viewing_sales)
        
        await _show_sales(message, sales, selected_date, is_callback=False)
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат даты!\n"
            "Используйте формат: ДД.ММ.ГГГГ (например, 15.10.2024)\n"
            "Или выберите дату из списка выше."
        )


@router.callback_query(ViewSalesStates.waiting_for_date, F.data.startswith("date_"))
async def select_sale_date(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Handle sale date selection from inline keyboard."""
    date_str = callback.data.split("_", 1)[1]
    selected_date = date.fromisoformat(date_str)
    
    sales = await SaleService.get_sales_by_date(session, selected_date)
    
    if not sales:
        await callback.message.edit_text(
            f"📋 На {selected_date.strftime('%d.%m.%Y')} продаж не было."
        )
        await state.clear()
        await callback.answer()
        return
    
    await state.update_data(sale_date=date_str, sale_date_obj=selected_date)
    await state.set_state(ViewSalesStates.viewing_sales)
    
    await _show_sales(callback, sales, selected_date, is_callback=True)


@router.callback_query(ViewSalesStates.viewing_sales, F.data.startswith("delete_sale_"))
async def delete_sale(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Handle sale deletion."""
    sale_id = int(callback.data.split("_")[-1])
    
    # Get sale info before deletion
    result = await session.execute(
        select(Sale)
        .options(
            selectinload(Sale.product),
            selectinload(Sale.seller)
        )
        .where(Sale.id == sale_id)
    )
    sale = result.scalar_one_or_none()
    
    if not sale:
        await callback.answer("Продажа не найдена", show_alert=True)
        return
    
    product_name = sale.product.name
    quantity = sale.quantity
    revenue = sale.sale_price * sale.quantity
    
    # Delete the sale
    success = await SaleService.delete_sale(session, sale_id)
    
    if success:
        await callback.message.edit_text(
            f"✅ <b>Продажа удалена</b>\n\n"
            f"Товар: {product_name}\n"
            f"Количество: {quantity} шт.\n"
            f"Выручка: {revenue} сом\n"
            f"Прибыль: {sale.profit:.2f} сом",
            parse_mode="HTML"
        )
        await callback.answer("Продажа удалена")
    else:
        await callback.answer("Ошибка при удалении", show_alert=True)

