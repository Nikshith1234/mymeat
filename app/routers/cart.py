"""
Cart router — endpoints for managing the session-based shopping cart.
Called by Rock8 voice agent tool calls.

SESSION DESIGN:
  The cart key is resolved server-side in this priority order:
    1. X-Caller-Number header (injected by Rock8/SIP — most reliable)
    2. caller_number body param (AI passes from call metadata)
    3. session_id body param (last resort fallback)
  This means the AI does NOT need to remember or track any session ID.
  The same caller phone = same cart throughout the entire call.
"""
import re
import logging
import uuid as _uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.database import get_db
from app.models.cart import Cart
from app.schemas.cart_schema import (
    AddToCartRequest,
    CalculateTotalRequest,
    CartResponse,
    CalculateTotalResponse,
    CartItemSchema,
    RemoveFromCartRequest,
)
from app.services.menu_service import validate_item

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Cart"])


def _normalize_phone(raw: str) -> str:
    """Strip formatting from phone number and return digits+leading+ only."""
    return re.sub(r"[\s\-\(\)]", "", raw.strip())


def _resolve_session(raw_request: Request, caller_number: Optional[str], session_id: str) -> str:
    """
    Resolve the cart session key from available sources, in priority order:
      1. X-Caller-Number SIP header (most reliable — injected by Rock8)
      2. caller_number body param (AI passes from call metadata)
      3. session_id body param (fallback — AI-generated UUID or whatever)

    If source 1 or 2 provide a numeric phone, we use them directly (digits normalized).
    Using the phone number as the cart key means the same caller maps to the same
    cart across ALL tool calls in a session — no AI memory required.
    """
    # Priority 1: Rock8 SIP header
    header_phone = raw_request.headers.get("x-caller-number", "").strip()
    if header_phone and not header_phone.startswith("{"):
        digits = _normalize_phone(header_phone)
        if digits and digits.lstrip("+").isdigit():
            logger.info(f"[SESSION] Resolved from SIP header: {digits}")
            return digits

    # Priority 2: caller_number body param
    if caller_number:
        digits = _normalize_phone(caller_number)
        if digits and digits.lstrip("+").isdigit() and len(digits) >= 7:
            logger.info(f"[SESSION] Resolved from caller_number param: {digits}")
            return digits

    # Priority 3: session_id fallback (use as-is — could be UUID or anything)
    logger.info(f"[SESSION] Using session_id as fallback: {session_id}")
    return session_id.strip()


def _get_or_create_cart(db: Session, session_key: str) -> Cart:
    """Get existing cart or create new one for the session."""
    cart = db.query(Cart).filter(Cart.session_id == session_key).first()
    if cart is None:
        cart = Cart(session_id=session_key, items=[], total_amount=0.0)
        db.add(cart)
        db.commit()
        db.refresh(cart)
    return cart


def _recalculate_total(items: list) -> float:
    """Recalculate total from cart items."""
    return sum(item.get("final_price", 0) for item in items)


@router.post("/add_to_cart", response_model=CartResponse)
async def add_to_cart(
    request: AddToCartRequest,
    raw_request: Request,
    db: Session = Depends(get_db),
):
    """
    Add an item to the cart.
    Cart session is resolved server-side from caller identity — AI does not need to track this.
    """
    session_key = _resolve_session(raw_request, request.caller_number, request.session_id)

    print(f"\n==============================================")
    print(f"📞 Riya CALLED: ADD TO CART")
    print(f"📞 SESSION KEY: {session_key}")
    print(f"📞 ITEM: {request.item_name} | VARIATION: {request.variation} | QTY: {request.quantity}")
    print(f"==============================================\n")

    logger.info(f"[CART] add_to_cart: key={session_key}, item={request.item_name}, var={request.variation}, qty={request.quantity}")

    try:
        item_info = await validate_item(request.item_name, request.variation)
    except ValueError as e:
        logger.warning(f"Menu validation failed: {e}")
        return CartResponse(success=False, message=str(e), cart_items=[], cart_total=0.0)
    except Exception as e:
        logger.error(f"Menu service error: {e}")
        raise HTTPException(status_code=503, detail="Menu service unavailable")

    cart = _get_or_create_cart(db, session_key)
    current_items = list(cart.items) if cart.items else []

    # Check for duplicate item+variation — increment quantity if found
    found = False
    for existing_item in current_items:
        if (
            existing_item.get("item_name", "").lower() == item_info["item_name"].lower()
            and existing_item.get("variation") == item_info["variation"]
        ):
            existing_item["quantity"] += request.quantity
            existing_item["final_price"] = existing_item["quantity"] * existing_item["price"]
            found = True
            logger.info(f"Incremented '{item_info['item_name']}' to qty={existing_item['quantity']}")
            break

    if not found:
        new_item = {
            "item_name": item_info["item_name"],
            "variation": item_info["variation"],
            "quantity": request.quantity,
            "price": item_info["price"],
            "final_price": item_info["price"] * request.quantity,
        }
        current_items.append(new_item)
        logger.info(f"Added new item '{item_info['item_name']}' to cart")

    cart.items = current_items
    cart.total_amount = _recalculate_total(current_items)
    flag_modified(cart, "items")
    db.commit()
    db.refresh(cart)

    return CartResponse(
        success=True,
        message=f"'{item_info['item_name']}' added to cart successfully",
        cart_items=[CartItemSchema(**item) for item in current_items],
        cart_total=cart.total_amount,
    )


@router.post("/calculate_total", response_model=CalculateTotalResponse)
async def calculate_total(
    request: CalculateTotalRequest,
    raw_request: Request,
    db: Session = Depends(get_db),
):
    """Return full cart contents and total amount."""
    session_key = _resolve_session(raw_request, request.caller_number, request.session_id)

    print(f"\n==============================================")
    print(f"📞 Riya CALLED: CALCULATE TOTAL")
    print(f"📞 SESSION KEY: {session_key}")
    print(f"==============================================\n")

    logger.info(f"[CART] calculate_total: key={session_key}")

    cart = db.query(Cart).filter(Cart.session_id == session_key).first()

    if cart is None or not cart.items:
        return CalculateTotalResponse(
            success=True,
            message="Cart is empty",
            cart_items=[],
            total_amount=0.0,
            item_count=0,
        )

    return CalculateTotalResponse(
        success=True,
        message="Cart total calculated",
        cart_items=[CartItemSchema(**item) for item in cart.items],
        total_amount=cart.total_amount,
        item_count=sum(item.get("quantity", 0) for item in cart.items),
    )


@router.post("/remove_from_cart", response_model=CartResponse)
async def remove_from_cart(
    request: RemoveFromCartRequest,
    raw_request: Request,
    db: Session = Depends(get_db),
):
    """Remove an item from the cart by name and optional variation."""
    session_key = _resolve_session(raw_request, request.caller_number, request.session_id)

    print(f"\n==============================================")
    print(f"📞 Riya CALLED: REMOVE FROM CART")
    print(f"📞 SESSION KEY: {session_key}")
    print(f"📞 ITEM: {request.item_name}")
    print(f"==============================================\n")

    logger.info(f"[CART] remove_from_cart: key={session_key}, item={request.item_name}")

    cart = db.query(Cart).filter(Cart.session_id == session_key).first()

    if cart is None or not cart.items:
        return CartResponse(
            success=False,
            message="Cart is empty, nothing to remove",
            cart_items=[],
            cart_total=0.0,
        )

    current_items = list(cart.items)
    original_len = len(current_items)

    current_items = [
        item for item in current_items
        if not (
            item.get("item_name", "").lower() == request.item_name.lower()
            and (request.variation is None or item.get("variation") == request.variation)
        )
    ]

    if len(current_items) == original_len:
        return CartResponse(
            success=False,
            message=f"Item '{request.item_name}' not found in cart",
            cart_items=[CartItemSchema(**i) for i in current_items],
            cart_total=cart.total_amount,
        )

    cart.items = current_items
    cart.total_amount = _recalculate_total(current_items)
    flag_modified(cart, "items")
    db.commit()
    db.refresh(cart)

    return CartResponse(
        success=True,
        message=f"'{request.item_name}' removed from cart",
        cart_items=[CartItemSchema(**i) for i in current_items],
        cart_total=cart.total_amount,
    )
