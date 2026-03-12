"""
Pydantic schemas for Order-related request/response models.
"""
from typing import Optional, List
from pydantic import BaseModel, Field
from app.schemas.cart_schema import CartItemSchema


class PlaceOrderRequest(BaseModel):
    """Request body for placing an order."""
    session_id: str = Field(..., description="Unique session ID for the cart (UUID generated at call start)")
    caller_number: Optional[str] = Field(None, description="Caller's actual phone number from metadata (e.g. +919876543210). Optional.")
    customer_phone: Optional[str] = Field(None, description="Customer phone number. Optional, same as caller_number.")
    customer_name: str = Field(..., description="Customer name")
    address: Optional[str] = Field(None, description="Delivery address (required for DELIVERY)")
    order_type: str = Field("PICKUP", description="DELIVERY or PICKUP")
    arrival_time: Optional[str] = Field(None, description="Expected pickup time (only for PICKUP orders)")


class PlaceOrderResponse(BaseModel):
    """Response after placing an order."""
    success: bool
    message: str
    order_id: Optional[str] = None
    total_amount: float = 0.0
    payment_link: Optional[str] = None
    items: List[CartItemSchema] = []


class PaymentWebhookPayload(BaseModel):
    """
    Razorpay webhook event payload.
    The actual structure is nested; we extract what we need.
    """
    event: str
    payload: dict


class PushToPosRequest(BaseModel):
    """Request to manually push an order to POS."""
    order_id: str = Field(..., description="The unique order ID to push")


class PushToPosResponse(BaseModel):
    """Response after POS push attempt."""
    success: bool
    message: str
    order_id: str
    pos_status: str


class OrderStatusResponse(BaseModel):
    """Response for checking order status."""
    success: bool
    order_id: str
    payment_status: str
    pos_status: str
    total_amount: float
    items: List[CartItemSchema] = []


class OrderSchema(BaseModel):
    """Full representation of an order for a list response."""
    order_id: str
    customer_name: str
    customer_phone: str
    address: Optional[str] = None
    order_type: str
    payment_status: str
    pos_status: str
    total_amount: float
    status: str = "pending"
    items: List[CartItemSchema] = []
    timestamp: Optional[str] = None
    arrival_time: Optional[str] = None

    class Config:
        from_attributes = True



class PlaceOrderResponse(BaseModel):
    """Response after placing an order."""
    success: bool
    message: str
    order_id: Optional[str] = None
    total_amount: float = 0.0
    payment_link: Optional[str] = None
    items: List[CartItemSchema] = []


class PaymentWebhookPayload(BaseModel):
    """
    Razorpay webhook event payload.
    The actual structure is nested; we extract what we need.
    """
    event: str
    payload: dict


class PushToPosRequest(BaseModel):
    """Request to manually push an order to POS."""
    order_id: str = Field(..., description="The unique order ID to push")


class PushToPosResponse(BaseModel):
    """Response after POS push attempt."""
    success: bool
    message: str
    order_id: str
    pos_status: str


class OrderStatusResponse(BaseModel):
    """Response for checking order status."""
    success: bool
    order_id: str
    payment_status: str
    pos_status: str
    total_amount: float
    items: List[CartItemSchema] = []


class OrderSchema(BaseModel):
    """Full representation of an order for a list response."""
    order_id: str
    customer_name: str
    customer_phone: str
    address: Optional[str] = None
    order_type: str
    payment_status: str
    pos_status: str
    total_amount: float
    status: str = "pending"
    items: List[CartItemSchema] = []
    timestamp: Optional[str] = None
    
    class Config:
        from_attributes = True
