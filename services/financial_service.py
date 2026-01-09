from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from database.models import FinancialSettings
from config import settings


class FinancialService:
    """Service for financial settings management."""
    
    @staticmethod
    async def create_financial_settings(
        session: AsyncSession,
        cny_to_som_rate: Decimal,
        delivery_cost_per_kg: Decimal,
        notes: Optional[str] = None,
    ) -> FinancialSettings:
        """Create new financial settings."""
        # Deactivate all previous settings
        result = await session.execute(
            select(FinancialSettings).where(FinancialSettings.is_active == True)
        )
        previous_settings = result.scalars().all()
        for prev in previous_settings:
            prev.is_active = False
        
        # Create new settings
        financial_settings = FinancialSettings(
            cny_to_som_rate=cny_to_som_rate,
            delivery_cost_per_kg=delivery_cost_per_kg,
            effective_from=datetime.now(timezone.utc),
            is_active=True,
            notes=notes,
        )
        session.add(financial_settings)
        await session.commit()
        await session.refresh(financial_settings)
        return financial_settings
    
    @staticmethod
    async def get_current_settings(session: AsyncSession) -> Optional[FinancialSettings]:
        """Get current active financial settings."""
        result = await session.execute(
            select(FinancialSettings)
            .where(FinancialSettings.is_active == True)
            .order_by(
                FinancialSettings.effective_from.desc(),
                FinancialSettings.id.desc(),
            )
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_or_create_default_settings(session: AsyncSession) -> FinancialSettings:
        """Get current settings or create default ones."""
        current = await FinancialService.get_current_settings(session)
        if current:
            return current
        
        # Create default settings
        return await FinancialService.create_financial_settings(
            session,
            Decimal(str(settings.default_cny_rate)),
            Decimal(str(settings.default_delivery_cost_per_kg)),
            notes="Начальные настройки по умолчанию"
        )
    
    @staticmethod
    async def get_all_settings(session: AsyncSession) -> list[FinancialSettings]:
        """Get all financial settings history."""
        result = await session.execute(
            select(FinancialSettings).order_by(FinancialSettings.effective_from.desc())
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def get_settings_for_date(session: AsyncSession, target_date: datetime) -> Optional[FinancialSettings]:
        """Get financial settings that were active on a specific date.
        
        Returns the settings record with effective_from <= target_date, ordered by effective_from desc.
        If no settings found, returns None.
        """
        if target_date.tzinfo is None:
            target_dt_utc = target_date.replace(tzinfo=timezone.utc)
        else:
            target_dt_utc = target_date.astimezone(timezone.utc)

        result = await session.execute(
            select(FinancialSettings)
            .where(FinancialSettings.effective_from <= target_dt_utc)
            .order_by(
                FinancialSettings.effective_from.desc(),
                FinancialSettings.id.desc(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def update_settings(
        session: AsyncSession,
        cny_to_som_rate: Optional[Decimal] = None,
        delivery_cost_per_kg: Optional[Decimal] = None,
        notes: Optional[str] = None,
    ) -> FinancialSettings:
        """Update financial settings by creating new record."""
        current = await FinancialService.get_current_settings(session)
        
        new_cny_rate = cny_to_som_rate if cny_to_som_rate is not None else (
            current.cny_to_som_rate if current else Decimal(str(settings.default_cny_rate))
        )
        new_delivery_cost = delivery_cost_per_kg if delivery_cost_per_kg is not None else (
            current.delivery_cost_per_kg if current else Decimal(str(settings.default_delivery_cost_per_kg))
        )
        
        return await FinancialService.create_financial_settings(
            session,
            new_cny_rate,
            new_delivery_cost,
            notes
        )

