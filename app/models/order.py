"""
Order and OrderItem SQLAlchemy models.
"""
import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Enum, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import relationship
from app.database import Base


class OrderType(str, enum.Enum):
    DELIVERY = "DELIVERY"
    PICKUP = "PICKUP"


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"


class PosStatus(str, enum.Enum):
    NOT_SENT = "NOT_SENT"
    SENT = "SENT"
    FAILED = "FAILED"


class KitchenStatus(str, enum.Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    READY = "ready"


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String(20), unique=True, nullable=False, index=True)
    customer_phone = Column(String(20), nullable=False)
    customer_name = Column(String(100), nullable=False)
    address = Column(Text, nullable=True)
    order_type = Column(Enum(OrderType), nullable=False, default=OrderType.PICKUP)
    total_amount = Column(Float, nullable=False, default=0.0)
    payment_status = Column(
        Enum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING
    )
    pos_status = Column(
        Enum(PosStatus), nullable=False, default=PosStatus.NOT_SENT
    )
    kitchen_status = Column(
        Enum(KitchenStatus), nullable=False, default=KitchenStatus.PENDING
    )
    razorpay_payment_link_id = Column(String(100), nullable=True)
    razorpay_payment_id = Column(String(100), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Order {self.order_id} - {self.payment_status}>"


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String(20), ForeignKey("orders.order_id"), nullable=False)
    item_name = Column(String(200), nullable=False)
    variation = Column(String(100), nullable=True)
    quantity = Column(Integer, nullable=False, default=1)
    price = Column(Float, nullable=False)
    final_price = Column(Float, nullable=False)

    # Relationship
    order = relationship("Order", back_populates="items")

    def __repr__(self):
        return f"<OrderItem {self.item_name} x{self.quantity}>"
