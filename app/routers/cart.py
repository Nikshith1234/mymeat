"""
Cart router — endpoints for managing the session-based shopping cart.
Called by Ultravox tool-calling agent.
"""
import logging
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


def _get_or_create_cart(db: Session, session_id: str) -> Cart:
    """Get existing cart or create new one for the session."""
    cart = db.query(Cart).filter(Cart.session_id == session_id).first()
    if cart is None:
        cart = Cart(session_id=session_id, items=[], total_amount=0.0)
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
    Add an item to the cart. Validates item against the menu.
    If item+variation already exists, increments quantity.
    """
    # ── Log all headers to find real caller number from Rock8 ──
    rock8_headers = dict(raw_request.headers)
    logger.info(f"[ROCK8 HEADERS] add_to_cart called. Headers: {rock8_headers}")
    logger.info(f"[ROCK8 HEADERS] session_id from AI: {request.session_id}")
    logger.info(
        f"Adding to cart: session={request.session_id}, "
        f"item={request.item_name}, variation={request.variation}, "
        f"qty={request.quantity}"
    )

    # Validate item against menu
    try:
        item_info = await validate_item(request.item_name, request.variation)
    except ValueError as e:
        logger.warning(f"Menu validation failed: {e}")
        return CartResponse(
            success=False,
            message=str(e),
            cart_items=[],
            cart_total=0.0,
        )
    except Exception as e:
        logger.error(f"Menu service error: {e}")
        raise HTTPException(status_code=503, detail="Menu service unavailable")

    # Get or create cart
    cart = _get_or_create_cart(db, request.session_id)
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
            logger.info(
                f"Incremented quantity for '{item_info['item_name']}' "
                f"to {existing_item['quantity']}"
            )
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

    # Update cart — reassign and flag as modified so SQLAlchemy detects the mutation
    cart.items = current_items
    cart.total_amount = _recalculate_total(current_items)
    flag_modified(cart, "items")
    db.commit()
    db.refresh(cart)

    # Build response
    cart_items_schema = [
        CartItemSchema(**item) for item in current_items
    ]

    return CartResponse(
        success=True,
        message=f"'{item_info['item_name']}' added to cart successfully",
        cart_items=cart_items_schema,
        cart_total=cart.total_amount,
    )


@router.post("/calculate_total", response_model=CalculateTotalResponse)
async def calculate_total(
    request: CalculateTotalRequest,
    db: Session = Depends(get_db),
):
    """Return full cart contents and total amount."""
    logger.info(f"Calculating total for session={request.session_id}")

    cart = db.query(Cart).filter(Cart.session_id == request.session_id).first()

    if cart is None or not cart.items:
        return CalculateTotalResponse(
            success=True,
            message="Cart is empty",
            cart_items=[],
            total_amount=0.0,
            item_count=0,
        )

    cart_items_schema = [
        CartItemSchema(**item) for item in cart.items
    ]

    return CalculateTotalResponse(
        success=True,
        message="Cart total calculated",
        cart_items=cart_items_schema,
        total_amount=cart.total_amount,
        item_count=sum(item.get("quantity", 0) for item in cart.items),
    )


@router.post("/remove_from_cart", response_model=CartResponse)
async def remove_from_cart(
    request: RemoveFromCartRequest,
    db: Session = Depends(get_db),
):
    """Remove an item from the cart by name and optional variation."""
    logger.info(
        f"Removing from cart: session={request.session_id}, "
        f"item={request.item_name}, variation={request.variation}"
    )

    cart = db.query(Cart).filter(Cart.session_id == request.session_id).first()

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
            and (
                request.variation is None
                or item.get("variation") == request.variation
            )
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
