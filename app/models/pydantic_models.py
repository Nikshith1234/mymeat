"""
Pydantic models for MongoDB documents.
These replace the previous SQLAlchemy models.
"""
from typing import List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class OrderType(str, Enum):
    DELIVERY = "DELIVERY"
    PICKUP = "PICKUP"

class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"

class PosStatus(str, Enum):
    NOT_SENT = "NOT_SENT"
    SENT = "SENT"
    FAILED = "FAILED"

class KitchenStatus(str, Enum):
    PENDING = "pending"
    AWAITING_PAYMENT = "awaiting_payment"
    PAID = "paid"
    PREPARING = "preparing"
    READY = "ready"

class MongoOrderItem(BaseModel):
    item_name: str
    variation: Optional[str] = None
    quantity: int = 1
    price: float
    final_price: float

class MongoOrder(BaseModel):
    order_id: str
    customer_phone: str
    customer_name: str
    address: Optional[str] = None
    order_type: OrderType = OrderType.PICKUP
    arrival_time: Optional[str] = None
    total_amount: float = 0.0
    payment_status: PaymentStatus = PaymentStatus.PENDING
    pos_status: PosStatus = PosStatus.NOT_SENT
    kitchen_status: KitchenStatus = KitchenStatus.PENDING
    razorpay_payment_link_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    items: List[MongoOrderItem] = []
    
    # Let MongoDB create the `_id` field 
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class MongoCart(BaseModel):
    session_id: str
    items: List[dict] = []
    total_amount: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class User(BaseModel):
    username: str
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
