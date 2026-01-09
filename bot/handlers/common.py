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
        "📚 <b>Справка</b>\n\n"
        "Основные действия доступны через кнопки меню (2 столбца). Ниже — команды для быстрого доступа:\n\n"
        
        "📦 <b>Товары</b>\n"
        "/add_product — добавить товар (после веса бот спросит цену продажи по умолчанию)\n"
        "/products — список товаров\n"
        "/stock — остатки на складе\n"
        "/edit_product — изменить данные товара (название, цены, вес, описание)\n"
        "/delete_product — деактивировать товар (скрыть из списков, данные сохраняются)\n\n"
        
        "🚚 <b>Поставки</b>\n"
        "/new_supply — создать заказ из Китая\n"
        "/update_supply — обновить статус заказа\n"
        "/delete_supply — удалить заказ и очистить складские данные\n"
        "Автообновление: пришлите боту сообщение о прибытии с трек-номерами — статусы отметятся автоматически.\n\n"
        
        "💰 <b>Продажи</b>\n"
        "/sale — зарегистрировать продажу (или кнопка ‘💰 Продажа’ в меню)\n"
        "Быстрое добавление: отправьте сообщение вида ‘Название 2 1000’ — продавец определяется по вашему Telegram ID.\n"
        "/today_sales — продажи за сегодня\n"
        "/month_sales — продажи за месяц\n\n"
        
        "📤 <b>Экспорт</b>\n"
        "/export_excel — выгрузка бухгалтерии в Excel (с поровну: Андрей/Женя)\n\n"
        
        "⚙️ <b>Настройки</b>\n"
        "Кнопка ‘Настройки’: управление продавцами и финансовыми параметрами (курс CNY, доставка за кг).\n"
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

