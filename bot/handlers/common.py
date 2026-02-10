from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import get_main_menu_keyboard, get_settings_keyboard
from database.models import User

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, user: User):
    """Handle /start command."""
    welcome_text = (
        f"👋 Добро пожаловать, {user.full_name}!\n\n"
        "🤖 Я бот для учёта товаров и продаж магазина кофейных аксессуаров.\n\n"
        "📋 Основные функции:\n"
        "• Управление товарами и складом\n"
        "• Учёт заказов из Китая\n"
        "• Регистрация продаж\n"
        "• Финансовая аналитика\n"
        "• Отчёты и статистика\n\n"
        "Используйте меню ниже или команду /help для справки."
    )
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_menu_keyboard()
    )


@router.message(Command("help"))
@router.message(F.text == "ℹ️ Помощь")
async def cmd_help(message: Message):
    """Handle /help command."""
    help_text = (
        "📚 <b>Справка по боту</b>\n\n"
        "Действия доступны через кнопки меню и команды ниже.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📦 <b>Товары</b>\n"
        "• <b>📦 Товары</b> или /products — список товаров\n"
        "• <b>➕ Добавить товар</b> или /add_product — новый товар (название, цена CNY, вес, цена продажи)\n"
        "• /edit_product — изменить товар (название, цены, вес, описание)\n"
        "• /delete_product — деактивировать товар\n\n"
        "📊 <b>Склад</b>\n"
        "• <b>📊 Склад</b> или /stock — остатки на складе и кнопки:\n"
        "  · <b>📤 Выдать со склада</b> — кто какой товар взял (продавец → товар → количество)\n"
        "  · <b>👥 Остатки у продавцов</b> — сколько у кого на руках (выдано − продано)\n"
        "• Быстрый ввод выдачи: <code>взять Название 5</code> или <code>взять 2 5</code> (ID 2, 5 шт.) — себе\n"
        "• <i>Продать можно только то, что уже взято со склада.</i> Сначала выдача, потом продажа.\n\n"
        "🚚 <b>Поставки из Китая</b>\n"
        "• <b>➕ Новый заказ</b> или /new_supply — создать заказ (трек, дата, товары)\n"
        "• <b>🔄 Обновить заказ</b> или /update_supply — сменить статус (в пути → доставлен)\n"
        "• <b>🗑️ Удалить заказ</b> или /delete_supply — удалить заказ и складские данные\n"
        "• /supply_status — список заказов\n"
        "• <b>📋 Поступления по дате</b> или /view_supplies — поступления за выбранную дату\n"
        "• Сообщение с трек-номерами (📦 …) — бот предложит отметить заказы как доставленные\n\n"
        "💰 <b>Продажи</b>\n"
        "• <b>💰 Продажа</b> или /sale — товар → цена → количество → выбор продавца\n"
        "• Быстрый ввод: <code>Название товара 2 1000</code> (кол-во и цена) — продавец = вы\n"
        "• Ограничение: продавец не может продать больше, чем у него на руках (остаток после выдачи)\n"
        "• /today_sales — продажи за сегодня\n"
        "• /month_sales — продажи за месяц\n"
        "• <b>📋 Продажи по дате</b> или /view_sales — продажи за выбранную дату\n\n"
        "💵 <b>Финансы</b>\n"
        "• <b>⚙️ Настройки</b> → 💵 Финансы или /finance_settings — курс CNY, стоимость доставки за кг\n"
        "• /profit — прибыль (за период)\n\n"
        "📈 <b>Отчёты и экспорт</b>\n"
        "• <b>📈 Отчёты</b> — отчёт за день/месяц, статистика по продавцам\n"
        "• /report_daily, /report_monthly, /seller_stats\n"
        "• <b>📤 Экспорт Excel</b> или /export_excel — выгрузка в Excel\n\n"
        "⚙️ <b>Настройки</b>\n"
        "• 👥 Продавцы — добавить продавца\n"
        "• 💵 Финансы — курс юаня, доставка за кг\n\n"
        "❌ <b>Отмена</b> — кнопка отменяет текущее действие (ввод, выбор)."
    )
    await message.answer(help_text, parse_mode="HTML")


@router.message(F.text == "⚙️ Настройки")
async def open_settings(message: Message):
    """Open settings menu."""
    await message.answer(
        "⚙️ <b>Настройки</b>\n\nВыберите раздел:",
        parse_mode="HTML",
        reply_markup=get_settings_keyboard()
    )


@router.message(F.text == "❌ Отмена")
async def cancel_action(message: Message, state: FSMContext):
    """Cancel current action."""
    await state.clear()
    await message.answer(
        "❌ Действие отменено.",
        reply_markup=get_main_menu_keyboard()
    )

