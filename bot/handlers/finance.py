from decimal import Decimal, InvalidOperation
import logging
from datetime import datetime, date, timedelta
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states import FinanceSettingsStates, SettingsStates
from bot.keyboards import get_main_menu_keyboard, get_cancel_keyboard, get_finance_settings_keyboard, get_settings_keyboard, get_sellers_manage_keyboard
from services.user_service import UserService
from services.financial_service import FinancialService
from services.sale_service import SaleService
from database.models import User

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("finance_settings"))
async def cmd_finance_settings(message: Message, state: FSMContext, session: AsyncSession):
    """Show financial settings menu."""
    logger.info(
        "[finance] Opening finance settings menu for user=%s",
        getattr(getattr(message, 'from_user', None), 'id', None),
    )
    await state.set_state(FinanceSettingsStates.waiting_for_action)
    
    current_settings = await FinancialService.get_or_create_default_settings(session)
    logger.info("[finance] Current settings: cny=%s, delivery=%s", current_settings.cny_to_som_rate, current_settings.delivery_cost_per_kg)
    
    await message.answer(
        f"💵 <b>Финансовые настройки</b>\n\n"
        f"📊 <b>Текущие параметры:</b>\n"
        f"💱 Курс CNY → SOM: <b>{current_settings.cny_to_som_rate}</b>\n"
        f"🚚 Доставка за кг: <b>{current_settings.delivery_cost_per_kg} сом</b>\n"
        f"📅 Действуют с: {current_settings.effective_from.strftime('%d.%m.%Y %H:%M')}\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=get_finance_settings_keyboard()
    )


## Removed 'current settings' inline action


@router.callback_query(FinanceSettingsStates.waiting_for_action, F.data == "finance_cny")
async def update_cny_rate(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Start updating CNY rate."""
    current_settings = await FinancialService.get_or_create_default_settings(session)
    logger.info(
        "[finance] Update CNY rate requested by user=%s; current=%s",
        getattr(getattr(callback, 'from_user', None), 'id', None),
        current_settings.cny_to_som_rate,
    )
    
    await state.set_state(FinanceSettingsStates.waiting_for_cny_rate)
    await callback.message.edit_text(
        f"💱 <b>Изменение курса юаня</b>\n\n"
        f"Текущий курс: <b>{current_settings.cny_to_som_rate} сом</b>\n\n"
        "Введите новый курс CNY → SOM:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(FinanceSettingsStates.waiting_for_cny_rate)
async def process_cny_rate(message: Message, state: FSMContext, session: AsyncSession):
    """Process new CNY rate."""
    try:
        logger.info(
            "[finance] Processing CNY rate input: raw='%s' user=%s",
            message.text,
            getattr(getattr(message, 'from_user', None), 'id', None),
        )
        new_rate = Decimal(message.text.replace(",", "."))
        if new_rate <= 0:
            raise ValueError("Rate must be positive")
        
        current_settings = await FinancialService.get_or_create_default_settings(session)
        new_settings = await FinancialService.update_settings(
            session,
            cny_to_som_rate=new_rate,
            notes=f"Обновлён курс юаня (было {current_settings.cny_to_som_rate})"
        )
        logger.info("[finance] CNY rate updated: old=%s new=%s", current_settings.cny_to_som_rate, new_settings.cny_to_som_rate)
        
        await state.clear()
        
        await message.answer(
            f"✅ <b>Курс юаня обновлён!</b>\n\n"
            f"Старый курс: {current_settings.cny_to_som_rate} сом\n"
            f"Новый курс: <b>{new_settings.cny_to_som_rate} сом</b>\n\n"
            "Новый курс будет применяться ко всем последующим продажам.",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )
    except (InvalidOperation, ValueError):
        logger.warning("[finance] Invalid CNY rate input: '%s'", message.text)
        await message.answer(
            "❌ Ошибка! Введите корректное положительное число.\n"
            "Например: 12.5"
        )
    except Exception as e:
        logger.exception("[finance] Unexpected error while updating CNY rate: %s", e)
        await message.answer("❌ Непредвиденная ошибка при обновлении курса. Попробуйте ещё раз.")


@router.callback_query(FinanceSettingsStates.waiting_for_action, F.data == "finance_delivery")
async def update_delivery_cost(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Start updating delivery cost."""
    # Ensure there is an active settings record to read current values
    current_settings = await FinancialService.get_or_create_default_settings(session)
    logger.info(
        "[finance] Update delivery requested by user=%s; current=%s",
        getattr(getattr(callback, 'from_user', None), 'id', None),
        current_settings.delivery_cost_per_kg,
    )
    
    await state.set_state(FinanceSettingsStates.waiting_for_delivery_cost)
    await callback.message.edit_text(
        f"🚚 <b>Изменение стоимости доставки</b>\n\n"
        f"Текущая стоимость: <b>{current_settings.delivery_cost_per_kg} сом/кг</b>\n\n"
        "Введите новую стоимость доставки за кг:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(FinanceSettingsStates.waiting_for_delivery_cost)
async def process_delivery_cost(message: Message, state: FSMContext, session: AsyncSession):
    """Process new delivery cost."""
    try:
        logger.info(
            "[finance] Processing delivery input: raw='%s' user=%s",
            message.text,
            getattr(getattr(message, 'from_user', None), 'id', None),
        )
        new_cost = Decimal(message.text.replace(",", "."))
        if new_cost < 0:
            raise ValueError("Cost must be non-negative")
        
        # Ensure there is an active settings record before referencing its fields
        current_settings = await FinancialService.get_or_create_default_settings(session)
        new_settings = await FinancialService.update_settings(
            session,
            delivery_cost_per_kg=new_cost,
            notes=f"Обновлена стоимость доставки (было {current_settings.delivery_cost_per_kg})"
        )
        logger.info("[finance] Delivery cost updated: old=%s new=%s", current_settings.delivery_cost_per_kg, new_settings.delivery_cost_per_kg)
        
        await state.clear()
        
        await message.answer(
            f"✅ <b>Стоимость доставки обновлена!</b>\n\n"
            f"Старая стоимость: {current_settings.delivery_cost_per_kg} сом/кг\n"
            f"Новая стоимость: <b>{new_settings.delivery_cost_per_kg} сом/кг</b>\n\n"
            "Новая стоимость будет применяться ко всем последующим продажам.",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )
    except (InvalidOperation, ValueError):
        logger.warning("[finance] Invalid delivery input: '%s'", message.text)
        await message.answer(
            "❌ Ошибка! Введите корректное неотрицательное число.\n"
            "Например: 350"
        )
    except Exception as e:
        logger.exception("[finance] Unexpected error while updating delivery cost: %s", e)
        await message.answer("❌ Непредвиденная ошибка при обновлении стоимости доставки. Попробуйте ещё раз.")


@router.message(Command("profit"))
async def cmd_profit(message: Message, session: AsyncSession):
    """Show profit for different periods."""
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = datetime.combine(date.today(), datetime.max.time())
    
    # Today's profit
    today_profit = await SaleService.calculate_total_profit(session, today_start, today_end)
    
    # This week's profit
    week_start = datetime.combine(date.today() - timedelta(days=date.today().weekday()), datetime.min.time())
    week_profit = await SaleService.calculate_total_profit(session, week_start, today_end)
    
    # This month's profit
    month_start = datetime.combine(date.today().replace(day=1), datetime.min.time())
    month_profit = await SaleService.calculate_total_profit(session, month_start, today_end)
    
    # Last month's profit
    last_month_end = month_start - timedelta(seconds=1)
    last_month_start = datetime.combine(last_month_end.date().replace(day=1), datetime.min.time())
    last_month_profit = await SaleService.calculate_total_profit(session, last_month_start, last_month_end)
    
    text = (
        f"📈 <b>Прибыль по периодам:</b>\n\n"
        f"📅 <b>Сегодня:</b>\n"
        f"   {today_profit:.2f} сом\n\n"
        f"📅 <b>Эта неделя:</b>\n"
        f"   {week_profit:.2f} сом\n\n"
        f"📅 <b>Этот месяц:</b>\n"
        f"   {month_profit:.2f} сом\n\n"
        f"📅 <b>Прошлый месяц:</b>\n"
        f"   {last_month_profit:.2f} сом"
    )
    
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "💵 Финансы")
async def menu_finance(message: Message, state: FSMContext, session: AsyncSession):
    """Open finance settings (so user can update delivery cost or CNY rate)."""
    logger.info(
        "[finance] Opening via reply button for user=%s",
        getattr(getattr(message, 'from_user', None), 'id', None),
    )
    await cmd_finance_settings(message, state, session)


@router.callback_query(F.data == "settings_finance")
async def settings_finance(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await cmd_finance_settings(callback.message, state, session)
    await callback.answer()


@router.callback_query(F.data == "settings_sellers")
async def settings_sellers(callback: CallbackQuery, session: AsyncSession):
    sellers = await UserService.get_all_active_sellers(session)
    sellers_text = "\n".join([f"• {s.full_name} (ID: {s.telegram_id})" for s in sellers]) or "пока нет"
    await callback.message.edit_text(
        f"👥 <b>Продавцы</b>\n\n"
        f"Текущий список:\n{sellers_text}\n\n"
        f"Нажмите 'Добавить продавца', чтобы указать Telegram ID и имя.",
        parse_mode="HTML",
        reply_markup=get_sellers_manage_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "seller_add")
async def seller_add_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите данные продавца в формате: ID Имя (например: 123456789 Иван)",
    )
    await state.set_state(SettingsStates.waiting_for_seller_input)
    await callback.answer()


@router.message(SettingsStates.waiting_for_seller_input)
async def seller_add_process(message: Message, state: FSMContext, session: AsyncSession):
    try:
        parts = message.text.strip().split(maxsplit=1)
        telegram_id = int(parts[0])
        full_name = parts[1] if len(parts) > 1 else f"User {telegram_id}"
        user = await UserService.add_seller(session, telegram_id=telegram_id, full_name=full_name)
        await state.clear()
        await message.answer(
            f"✅ Продавец добавлен/активирован: {user.full_name} (ID: {user.telegram_id})",
            reply_markup=get_settings_keyboard()
        )
    except Exception:
        await message.answer("❌ Неверный формат. Пример: 123456789 Иван Иванов")

