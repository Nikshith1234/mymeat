"""
Pydantic schemas for Cart-related request/response models.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class AddToCartRequest(BaseModel):
    """Request body for adding an item to the cart."""
    session_id: str = Field(..., description="Unique session ID (UUID) for the cart")
    caller_number: Optional[str] = Field(None, description="Caller's actual phone number. Optional.")
    item_name: str = Field(..., description="Name of the menu item")
    variation: Optional[str] = Field(None, description="Item variation (e.g., Half, Full)")
    quantity: int = Field(1, ge=1, description="Quantity to add")


class CalculateTotalRequest(BaseModel):
    """Request body for calculating cart total."""
    session_id: str = Field(..., description="Unique session ID (UUID) for the cart")
    caller_number: Optional[str] = Field(None, description="Caller's actual phone number. Optional.")


class CartItemSchema(BaseModel):
    """Schema for a single item in the cart."""
    item_name: str
    variation: Optional[str] = None
    quantity: int
    price: float
    final_price: float


class CartResponse(BaseModel):
    """Standard response for cart operations."""
    success: bool
    message: str
    cart_items: List[CartItemSchema] = []
    cart_total: float = 0.0


class CalculateTotalResponse(BaseModel):
    """Response for calculate total endpoint."""
    success: bool
    message: str
    cart_items: List[CartItemSchema] = []
    total_amount: float = 0.0
    item_count: int = 0


class RemoveFromCartRequest(BaseModel):
    """Request body for removing an item from the cart."""
    session_id: str = Field(..., description="Unique session ID (UUID) for the cart")
    caller_number: Optional[str] = Field(None, description="Caller's actual phone number. Optional.")
    item_name: str = Field(..., description="Name of the menu item to remove")
    variation: Optional[str] = Field(None, description="Item variation")

