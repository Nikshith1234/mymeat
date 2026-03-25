"""
Pydantic schemas for Cart-related request/response models.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class AddToCartRequest(BaseModel):
    """Request body for adding an item to the cart."""
    session_id: str = Field(..., description="Unique session ID (UUID) for the cart")
    caller_number: Optional[str] = Field(None, description="Caller's actual phone number. Optional.")
    item_name: str = Field(..., description="Name of the menu item")
    variation: Optional[str] = Field(None, description="Item variation (e.g., 500 Grms, 1 Kg). Omit when using custom_weight_kg.")
    quantity: int = Field(1, ge=1, description="Quantity to add. Ignored when custom_weight_kg is set.")
    custom_weight_kg: Optional[float] = Field(
        None,
        gt=0,
        description=(
            "When set, bypasses standard variation and calculates exact price "
            "proportionally (price-per-gram × requested grams). "
            "Use for non-standard weights like 4.2 kg or 3.214 kg. "
            "Do NOT pass variation or quantity when this is set."
        ),
    )


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
    quantity: Optional[str] = Field(None, description="Weight to remove, e.g. '1 Kg', '500 Grms'. If omitted, removes entire item.")


# ── Price lookup schemas ───────────────────────────────────────────────────────

class GetItemPriceRequest(BaseModel):
    """Request to look up item pricing and optionally compute a budget allocation."""
    session_id: str = Field(..., description="Session ID (same 6-digit code used for cart calls)")
    item_name: str = Field(..., description="Exact menu item name to look up")
    budget: Optional[float] = Field(
        None,
        gt=0,
        description="Customer's budget in rupees. When provided, the response includes the maximum weight that can be purchased within this budget.",
    )
    custom_weight_kg: Optional[float] = Field(
        None,
        gt=0,
        description="Customer's requested weight in kg (e.g. 3.3, 0.75). When provided, the response includes the computed total price.",
    )


class VariationPriceInfo(BaseModel):
    """Pricing info for a single menu variation."""
    name: str
    price: float
    grams: int
    price_per_gram: float


class GetItemPriceResponse(BaseModel):
    """Response for get_item_price endpoint."""
    success: bool
    item_name: str
    price_per_gram: float = 0.0          # rupees per gram (from reference variation)
    price_per_kg: float = 0.0            # price_per_gram * 1000 — easier for AI to use
    variations: List[VariationPriceInfo] = []
    # Custom weight fields — populated when custom_weight_kg is provided
    custom_weight_kg: Optional[float] = None
    computed_total_price: Optional[float] = None  # server-computed total = weight_kg * price_per_kg
    # Budget fields — only populated when `budget` is provided
    budget: Optional[float] = None
    max_weight_grams: Optional[int] = None
    max_weight_kg: Optional[float] = None
    max_weight_human: Optional[str] = None   # e.g. "750 Grms" or "1.5 Kg"
    actual_cost: Optional[float] = None      # exact cost for max_weight_grams
    custom_weight_kg_to_add: Optional[float] = None  # pass this to add_to_cart
    message: str = ""


# ── Menu search schemas ────────────────────────────────────────────────────────

class SearchMenuRequest(BaseModel):
    """Request to search the menu."""
    session_id: str = Field(..., description="Unique session ID for the call")
    caller_number: Optional[str] = Field(None, description="Caller's phone number")
    query: Optional[str] = Field(None, description="Item name or category to search for (e.g. 'chicken', 'mutton boneless'). If empty, returns categories.")


class SearchMenuItemSchema(BaseModel):
    """Schema for a matched menu item."""
    name: str
    category: str
    description: str


class SearchMenuResponse(BaseModel):
    """Response for search_menu endpoint."""
    success: bool
    message: str
    items: List[SearchMenuItemSchema] = []
    categories: List[str] = []

