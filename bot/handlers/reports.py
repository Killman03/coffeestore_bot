from datetime import datetime, date, timedelta
from decimal import Decimal
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from services.sale_service import SaleService
from services.product_service import ProductService
from services.export_service import ExportService

router = Router()


@router.message(Command("report_daily"))
async def cmd_report_daily(message: Message, session: AsyncSession):
    """Generate daily report."""
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())
    
    # Get today's sales
    sales = await SaleService.get_sales_by_date_range(session, today_start, today_end)
    
    if not sales:
        await message.answer(
            f"📊 <b>Ежедневный отчёт за {today.strftime('%d.%m.%Y')}</b>\n\n"
            "Сегодня продаж не было."
        )
        return
    
    # Calculate totals
    total_sales = len(sales)
    total_quantity = sum(sale.quantity for sale in sales)
    total_revenue = sum(sale.sale_price * sale.quantity for sale in sales)
    total_cost = sum(sale.cost_price * sale.quantity for sale in sales)
    total_profit = sum(sale.profit for sale in sales)
    
    # Group by seller
    sellers_stats = {}
    for sale in sales:
        seller_name = sale.seller.full_name
        if seller_name not in sellers_stats:
            sellers_stats[seller_name] = {
                'sales': 0,
                'quantity': 0,
                'revenue': Decimal(0),
                'profit': Decimal(0),
            }
        sellers_stats[seller_name]['sales'] += 1
        sellers_stats[seller_name]['quantity'] += sale.quantity
        sellers_stats[seller_name]['revenue'] += sale.sale_price * sale.quantity
        sellers_stats[seller_name]['profit'] += sale.profit
    
    # Build report
    text = (
        f"📊 <b>Ежедневный отчёт за {today.strftime('%d.%m.%Y')}</b>\n\n"
        f"📦 <b>Общие показатели:</b>\n"
        f"Продаж: {total_sales} шт.\n"
        f"Товаров: {total_quantity} шт.\n"
        f"Выручка: {total_revenue} сом\n"
        f"Себестоимость: {total_cost:.2f} сом\n"
        f"Прибыль: <b>{total_profit:.2f} сом</b>\n"
        f"Рентабельность: <b>{(total_profit/total_revenue*100):.1f}%</b>\n\n"
    )
    
    if sellers_stats:
        text += "👥 <b>По продавцам:</b>\n"
        for seller_name, stats in sorted(sellers_stats.items(), key=lambda x: x[1]['profit'], reverse=True):
            text += (
                f"🔹 <b>{seller_name}</b>\n"
                f"   Продаж: {stats['sales']} | Товаров: {stats['quantity']} шт.\n"
                f"   Выручка: {stats['revenue']} сом | Прибыль: {stats['profit']:.2f} сом\n"
            )
    
    await message.answer(text, parse_mode="HTML")


@router.message(Command("report_monthly"))
async def cmd_report_monthly(message: Message, session: AsyncSession):
    """Generate monthly report."""
    today = date.today()
    month_start = datetime.combine(today.replace(day=1), datetime.min.time())
    if today.month == 12:
        month_end = datetime.combine(today.replace(year=today.year + 1, month=1, day=1), datetime.min.time()) - timedelta(seconds=1)
    else:
        month_end = datetime.combine(today.replace(month=today.month + 1, day=1), datetime.min.time()) - timedelta(seconds=1)
    
    # Get month sales
    sales = await SaleService.get_sales_by_date_range(session, month_start, month_end)
    
    if not sales:
        await message.answer(
            f"📊 <b>Месячный отчёт за {today.strftime('%B %Y')}</b>\n\n"
            "В этом месяце продаж не было."
        )
        return
    
    # Calculate totals
    total_sales = len(sales)
    total_quantity = sum(sale.quantity for sale in sales)
    total_revenue = sum(sale.sale_price * sale.quantity for sale in sales)
    total_cost = sum(sale.cost_price * sale.quantity for sale in sales)
    total_profit = sum(sale.profit for sale in sales)
    
    # Group by product
    products_stats = {}
    for sale in sales:
        product_name = sale.product.name
        if product_name not in products_stats:
            products_stats[product_name] = {
                'quantity': 0,
                'revenue': Decimal(0),
                'profit': Decimal(0),
            }
        products_stats[product_name]['quantity'] += sale.quantity
        products_stats[product_name]['revenue'] += sale.sale_price * sale.quantity
        products_stats[product_name]['profit'] += sale.profit
    
    # Get top products
    top_products = sorted(products_stats.items(), key=lambda x: x[1]['profit'], reverse=True)[:10]
    
    # Build report
    text = (
        f"📊 <b>Месячный отчёт за {today.strftime('%B %Y')}</b>\n\n"
        f"📦 <b>Общие показатели:</b>\n"
        f"Продаж: {total_sales} шт.\n"
        f"Товаров: {total_quantity} шт.\n"
        f"Выручка: {total_revenue} сом\n"
        f"Себестоимость: {total_cost:.2f} сом\n"
        f"Прибыль: <b>{total_profit:.2f} сом</b>\n"
        f"Рентабельность: <b>{(total_profit/total_revenue*100):.1f}%</b>\n\n"
    )
    
    if top_products:
        text += "🏆 <b>Топ-10 товаров:</b>\n"
        for i, (product_name, stats) in enumerate(top_products, 1):
            text += (
                f"{i}. <b>{product_name}</b>\n"
                f"   Продано: {stats['quantity']} шт. | Прибыль: {stats['profit']:.2f} сом\n"
            )
    
    await message.answer(text, parse_mode="HTML")


@router.message(Command("seller_stats"))
async def cmd_seller_stats(message: Message, session: AsyncSession):
    """Show seller statistics."""
    today = date.today()
    month_start = datetime.combine(today.replace(day=1), datetime.min.time())
    month_end = datetime.combine(today, datetime.max.time())
    
    # Get statistics
    stats = await SaleService.get_seller_statistics(session, month_start, month_end)
    
    if not stats:
        await message.answer(
            f"📊 <b>Статистика по продавцам за {today.strftime('%B %Y')}</b>\n\n"
            "В этом месяце продаж не было."
        )
        return
    
    text = f"📊 <b>Статистика по продавцам за {today.strftime('%B %Y')}</b>\n\n"
    
    for i, seller_stat in enumerate(stats, 1):
        avg_profit = seller_stat['total_profit'] / seller_stat['sales_count'] if seller_stat['sales_count'] > 0 else 0
        
        text += (
            f"{i}. <b>{seller_stat['seller_name']}</b>\n"
            f"   Продаж: {seller_stat['sales_count']} шт.\n"
            f"   Товаров: {seller_stat['total_quantity']} шт.\n"
            f"   Выручка: {seller_stat['total_revenue']} сом\n"
            f"   Прибыль: <b>{seller_stat['total_profit']:.2f} сом</b>\n"
            f"   Средняя прибыль: {avg_profit:.2f} сом/продажа\n\n"
        )
    
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "📈 Отчёты")
async def menu_reports(message: Message, session: AsyncSession):
    """Show reports menu."""
    await cmd_report_daily(message, session)


@router.message(Command("export_excel"))
@router.message(F.text == "📤 Экспорт Excel")
async def export_excel(message: Message, session: AsyncSession):
    """Export accounting data to Excel and send as file."""
    data = await ExportService.export_accounting_excel(session)
    from aiogram.types import BufferedInputFile
    file = BufferedInputFile(data, filename=f"accounting_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")
    await message.answer_document(
        document=file,
        caption="Экспорт бухгалтерии (поровну для Андрея и Жени)"
    )

