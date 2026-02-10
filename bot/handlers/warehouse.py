# noqa: D100
"""Handlers for warehouse issues (seller take from warehouse) and seller balances."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states import TakeFromWarehouseStates
from bot.keyboards import (
    get_main_menu_keyboard,
    get_cancel_keyboard,
    get_sellers_keyboard,
    get_products_keyboard,
    get_quantity_quick_keyboard,
)
from services.warehouse_issue_service import WarehouseIssueService
from services.product_service import ProductService
from services.user_service import UserService
from database.models import User

router = Router()


def _parse_quick_take(text: str) -> tuple[str | None, int | None]:
    """Parse 'взять <name_or_id> <qty>' or 'выдача <name_or_id> <qty>'. Returns (name_or_id, qty) or (None, None)."""
    t = (text or "").strip().lower()
    if not t:
        return None, None
    for prefix in ("взять ", "выдача "):
        if t.startswith(prefix):
            rest = t[len(prefix) :].strip()
            parts = rest.split()
            if len(parts) >= 2:
                try:
                    qty = int(parts[-1])
                    if qty <= 0:
                        return None, None
                except ValueError:
                    return None, None
                name_or_id = " ".join(parts[:-1]).strip()
                if name_or_id:
                    return name_or_id, qty
            break
    return None, None


@router.callback_query(F.data == "warehouse_issue_start")
async def warehouse_issue_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Start take-from-warehouse flow: choose seller."""
    await state.set_state(TakeFromWarehouseStates.waiting_for_seller)
    sellers = await UserService.get_all_active_sellers(session)
    if not sellers:
        await callback.message.edit_text(
            "❌ Нет активных продавцов. Добавьте продавца в настройках."
        )
        await state.clear()
        await callback.answer()
        return
    await callback.message.edit_text(
        "📤 <b>Выдача со склада</b>\n\nВыберите продавца:",
        parse_mode="HTML",
        reply_markup=get_sellers_keyboard(sellers),
    )
    await callback.answer()


@router.callback_query(
    TakeFromWarehouseStates.waiting_for_seller,
    F.data.startswith("seller_"),
)
async def warehouse_issue_seller(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    """Save seller and show product choice."""
    seller_id = int(callback.data.split("_")[1])
    seller_result = await session.execute(select(User).where(User.id == seller_id))
    seller = seller_result.scalar_one_or_none()
    if not seller:
        await callback.answer("Продавец не найден", show_alert=True)
        return
    await state.update_data(issue_seller_id=seller_id, issue_seller_name=seller.full_name)
    await state.set_state(TakeFromWarehouseStates.waiting_for_product)
    products = await ProductService.get_all_products(session)
    # Filter to products that have warehouse stock
    with_stock = []
    for p in products:
        wh = await WarehouseIssueService.get_warehouse_stock(session, p.id)
        if wh > 0:
            with_stock.append((p, wh))
    if not with_stock:
        await callback.message.edit_text(
            "❌ На складе нет товара для выдачи. Сначала оформите поставку."
        )
        await state.clear()
        await callback.answer()
        return
    products_only = [p for p, _ in with_stock]
    await callback.message.edit_text(
        f"📤 Выдача: <b>{seller.full_name}</b>\n\nВыберите товар:",
        parse_mode="HTML",
        reply_markup=get_products_keyboard(products_only),
    )
    await callback.answer()


@router.callback_query(
    TakeFromWarehouseStates.waiting_for_product,
    F.data.startswith("product_"),
)
async def warehouse_issue_product(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    """Save product and ask for quantity."""
    product_id = int(callback.data.split("_")[1])
    product = await ProductService.get_product_by_id(session, product_id)
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    available = await WarehouseIssueService.get_warehouse_stock(session, product_id)
    if available <= 0:
        await callback.answer("На складе нет этого товара", show_alert=True)
        return
    await state.update_data(
        issue_product_id=product_id,
        issue_product_name=product.name,
        issue_available=available,
    )
    await state.set_state(TakeFromWarehouseStates.waiting_for_quantity)
    await callback.message.edit_text(
        f"📤 <b>{product.name}</b>\n"
        f"Доступно на складе: <b>{available} шт.</b>\n\n"
        "Введите количество или выберите кнопку:",
        parse_mode="HTML",
        reply_markup=get_quantity_quick_keyboard(),
    )
    await callback.answer()


@router.callback_query(
    TakeFromWarehouseStates.waiting_for_quantity,
    F.data.startswith("issue_qty_"),
)
async def warehouse_issue_quantity_callback(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    """Process quantity from inline button."""
    qty = int(callback.data.split("_")[-1])
    await _do_create_issue(callback, state, session, qty, is_callback=True)


@router.message(TakeFromWarehouseStates.waiting_for_quantity, F.text)
async def warehouse_issue_quantity_message(
    message: Message, state: FSMContext, session: AsyncSession
):
    """Process quantity from text."""
    if (message.text or "").strip().lower() in ("отмена", "cancel", "❌ отмена"):
        await state.clear()
        await message.answer("❌ Действие отменено.", reply_markup=get_main_menu_keyboard())
        return
    try:
        qty = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Введите целое число (количество).")
        return
    if qty <= 0:
        await message.answer("❌ Количество должно быть больше нуля.")
        return
    data = await state.get_data()
    if qty > data.get("issue_available", 0):
        await message.answer(
            f"❌ На складе доступно только <b>{data['issue_available']} шт.</b>",
            parse_mode="HTML",
        )
        return
    issue = await WarehouseIssueService.create_issue(
        session,
        seller_id=data["issue_seller_id"],
        product_id=data["issue_product_id"],
        quantity=qty,
    )
    await state.clear()
    if not issue:
        await message.answer("❌ Не удалось оформить выдачу (недостаточно на складе).")
        return
    await message.answer(
        f"✅ <b>Выдача оформлена</b>\n\n"
        f"Продавец: <b>{issue.seller.full_name}</b>\n"
        f"Товар: <b>{issue.product.name}</b>\n"
        f"Количество: <b>{qty} шт.</b>",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(),
    )


async def _do_create_issue(callback, state, session, qty: int, *, is_callback: bool):
    """Create issue and edit/answer callback or message."""
    data = await state.get_data()
    if qty <= 0 or qty > data.get("issue_available", 0):
        if is_callback:
            await callback.answer("Недостаточно на складе", show_alert=True)
        return
    issue = await WarehouseIssueService.create_issue(
        session,
        seller_id=data["issue_seller_id"],
        product_id=data["issue_product_id"],
        quantity=qty,
    )
    await state.clear()
    if not issue:
        if is_callback:
            await callback.answer("Ошибка при выдаче", show_alert=True)
        return
    text = (
        f"✅ <b>Выдача оформлена</b>\n\n"
        f"Продавец: <b>{issue.seller.full_name}</b>\n"
        f"Товар: <b>{issue.product.name}</b>\n"
        f"Количество: <b>{qty} шт.</b>"
    )
    if is_callback:
        await callback.message.edit_text(text, parse_mode="HTML")
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=get_main_menu_keyboard(),
        )
        await callback.answer()
    else:
        await callback.answer(text, parse_mode="HTML")


@router.callback_query(F.data == "warehouse_seller_balances")
async def warehouse_seller_balances(callback: CallbackQuery, session: AsyncSession):
    """Show how much product each seller currently has (issued - sold)."""
    balances = await WarehouseIssueService.get_all_seller_balances(session)
    lines = ["👥 <b>Остатки у продавцов</b>\n"]
    has_any = False
    for seller, product_balances in balances:
        if not product_balances:
            continue
        has_any = True
        lines.append(f"\n<b>{seller.full_name}</b>")
        for product, balance in product_balances:
            lines.append(f"  • {product.name}: <b>{balance} шт.</b>")
    if not has_any:
        lines.append("\nНет остатков (никто не брал товар со склада или всё уже продано).")
    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
    )
    await callback.answer()


# ---- Quick input: "взять Название 5" or "взять 2 5" (product_id 5 qty) - for current user
@router.message(F.text)
async def quick_take_from_warehouse(
    message: Message, session: AsyncSession, user: User, state: FSMContext
):
    """Quick issue: 'взять <name or id> <qty>' or 'выдача ...' — issue to current user."""
    if await state.get_state():
        return
    name_or_id, qty = _parse_quick_take(message.text or "")
    if name_or_id is None or qty is None:
        return
    if not user:
        return
    seller_id = user.id
    product = None
    if name_or_id.isdigit():
        product = await ProductService.get_product_by_id(session, int(name_or_id))
    else:
        products = await ProductService.search_products(session, name_or_id)
        if len(products) == 1:
            product = products[0]
        elif len(products) > 1:
            await message.answer(
                "Найдено несколько товаров. Уточните название или введите ID.\n"
                "Формат быстрого ввода: <code>взять Название количество</code> или <code>взять ID количество</code>",
                parse_mode="HTML",
            )
            return
    if not product:
        await message.answer(
            f"❌ Товар не найден: «{name_or_id}». Используйте название или ID."
        )
        return
    available = await WarehouseIssueService.get_warehouse_stock(session, product.id)
    if qty > available:
        await message.answer(
            f"❌ Недостаточно на складе. Доступно: <b>{available} шт.</b>",
            parse_mode="HTML",
        )
        return
    issue = await WarehouseIssueService.create_issue(
        session, seller_id=seller_id, product_id=product.id, quantity=qty
    )
    if not issue:
        await message.answer("❌ Не удалось оформить выдачу.")
        return
    await message.answer(
        f"✅ <b>Выдача оформлена</b> (быстрый ввод)\n\n"
        f"Вам выдано: <b>{product.name}</b> — <b>{qty} шт.</b>",
        parse_mode="HTML",
    )
