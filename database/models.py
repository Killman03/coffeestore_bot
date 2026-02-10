from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import List

from sqlalchemy import String, Integer, BigInteger, Numeric, DateTime, ForeignKey, Boolean, Text, Enum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class User(Base):
    """User model - represents sellers and admins."""
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    sales: Mapped[List["Sale"]] = relationship("Sale", back_populates="seller")
    warehouse_issues: Mapped[List["WarehouseIssue"]] = relationship("WarehouseIssue", back_populates="seller")
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, name='{self.full_name}')>"


## Category model removed


class Product(Base):
    """Product model."""
    __tablename__ = "products"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_price_cny: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)  # Price in CNY
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)  # Weight in kg
    default_sale_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))  # Optional default sale price in SOM
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    supply_items: Mapped[List["SupplyOrderItem"]] = relationship("SupplyOrderItem", back_populates="product")
    sales: Mapped[List["Sale"]] = relationship("Sale", back_populates="product")
    warehouse_issues: Mapped[List["WarehouseIssue"]] = relationship("WarehouseIssue", back_populates="product")
    
    def calculate_cost(self, cny_rate: Decimal, delivery_cost_per_kg: Decimal) -> Decimal:
        """Calculate product cost in local currency."""
        return (self.base_price_cny * cny_rate) + (self.weight_kg * delivery_cost_per_kg)
    
    @property
    def total_received(self) -> int:
        """Calculate total quantity received from supply orders."""
        return sum(item.quantity for item in self.supply_items if item.supply_order.status == SupplyStatus.DELIVERED)
    
    @property
    def total_sold(self) -> int:
        """Calculate total quantity sold."""
        return sum(sale.quantity for sale in self.sales)
    
    @property
    def current_stock(self) -> int:
        """Calculate current stock quantity."""
        return self.total_received - self.total_sold
    
    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name='{self.name}')>"


class SupplyStatus(str, PyEnum):
    """Supply order status enum."""
    ORDERED = "ordered"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class SupplyOrder(Base):
    """Supply order from China model."""
    __tablename__ = "supply_orders"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tracking_number: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    order_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivery_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[SupplyStatus] = mapped_column(Enum(SupplyStatus), default=SupplyStatus.ORDERED)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    items: Mapped[List["SupplyOrderItem"]] = relationship("SupplyOrderItem", back_populates="supply_order", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<SupplyOrder(id={self.id}, tracking='{self.tracking_number}', status='{self.status}')>"


class SupplyOrderItem(Base):
    """Supply order item - products in supply order."""
    __tablename__ = "supply_order_items"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supply_order_id: Mapped[int] = mapped_column(Integer, ForeignKey("supply_orders.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    # Optional overrides captured on arrival: unit price in CNY and unit weight in kg
    unit_price_cny: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    unit_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    supply_order: Mapped["SupplyOrder"] = relationship("SupplyOrder", back_populates="items")
    product: Mapped["Product"] = relationship("Product", back_populates="supply_items")
    
    def __repr__(self) -> str:
        return f"<SupplyOrderItem(id={self.id}, product_id={self.product_id}, qty={self.quantity})>"


class WarehouseIssue(Base):
    """Record of a seller taking product from warehouse."""
    __tablename__ = "warehouse_issues"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    seller: Mapped["User"] = relationship("User", back_populates="warehouse_issues")
    product: Mapped["Product"] = relationship("Product", back_populates="warehouse_issues")
    
    def __repr__(self) -> str:
        return f"<WarehouseIssue(id={self.id}, seller_id={self.seller_id}, product_id={self.product_id}, qty={self.quantity})>"


class Sale(Base):
    """Sale model."""
    __tablename__ = "sales"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False)
    seller_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    sale_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)  # Price per unit in SOM
    cost_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)  # Cost per unit in SOM
    profit: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)  # Profit in SOM
    sale_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="sales")
    seller: Mapped["User"] = relationship("User", back_populates="sales")
    
    def __repr__(self) -> str:
        return f"<Sale(id={self.id}, product_id={self.product_id}, qty={self.quantity}, profit={self.profit})>"


class FinancialSettings(Base):
    """Financial settings model - stores current financial parameters."""
    __tablename__ = "financial_settings"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cny_to_som_rate: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    delivery_cost_per_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self) -> str:
        return f"<FinancialSettings(id={self.id}, cny_rate={self.cny_to_som_rate}, delivery={self.delivery_cost_per_kg})>"

