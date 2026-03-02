"""
Order router — handles order placement from cart.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cart import Cart
from app.models.order import Order, OrderItem, OrderType, PaymentStatus, PosStatus
from app.schemas.order_schema import PlaceOrderRequest, PlaceOrderResponse
from app.schemas.cart_schema import CartItemSchema
from app.utils.id_generator import generate_order_id
from app.services.razorpay_service import create_payment_link


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Orders"])


@router.post("/place_order", response_model=PlaceOrderResponse)
async def place_order(
    request: PlaceOrderRequest,
    db: Session = Depends(get_db),
):
    """
    Place an order from the current cart.

    Steps:
    1. Validate cart exists and is not empty
    2. Validate order_type and address
    3. Create Order + OrderItem records
    4. Generate Razorpay payment link
    5. Clear the cart
    6. Return payment link to caller
    """
    logger.info(
        f"Placing order: session={request.session_id}, "
        f"phone={request.customer_phone}, type={request.order_type}"
    )

    # ── Validate order type ──
    order_type_upper = request.order_type.upper()
    if order_type_upper not in ("DELIVERY", "PICKUP"):
        return PlaceOrderResponse(
            success=False,
            message="Invalid order_type. Must be DELIVERY or PICKUP.",
        )

    # ── Validate address for delivery ──
    if order_type_upper == "DELIVERY" and not request.address:
        return PlaceOrderResponse(
            success=False,
            message="Address is required for DELIVERY orders.",
        )

    # ── Get cart ──
    cart = db.query(Cart).filter(Cart.session_id == request.session_id).first()
    if cart is None or not cart.items:
        return PlaceOrderResponse(
            success=False,
            message="Cart is empty. Please add items before placing an order.",
        )

    cart_items = cart.items
    total_amount = cart.total_amount

    # ── Generate unique order ID ──
    order_id = generate_order_id()

    # Ensure uniqueness (very unlikely collision but handle it)
    while db.query(Order).filter(Order.order_id == order_id).first() is not None:
        order_id = generate_order_id()

    # ── Create Order record ──
    order = Order(
        order_id=order_id,
        customer_phone=request.customer_phone,
        customer_name=request.customer_name,
        address=request.address,
        order_type=OrderType(order_type_upper),
        total_amount=total_amount,
        payment_status=PaymentStatus.PENDING,
        pos_status=PosStatus.NOT_SENT,
    )
    db.add(order)

    # ── Create OrderItem records ──
    order_item_schemas = []
    for item in cart_items:
        order_item = OrderItem(
            order_id=order_id,
            item_name=item.get("item_name", ""),
            variation=item.get("variation"),
            quantity=item.get("quantity", 1),
            price=item.get("price", 0),
            final_price=item.get("final_price", 0),
        )
        db.add(order_item)
        order_item_schemas.append(CartItemSchema(**item))

    # ── Generate Razorpay payment link ──
    try:
        payment_result = create_payment_link(
            order_id=order_id,
            amount=total_amount,
            customer_phone=request.customer_phone,
            customer_name=request.customer_name,
        )
        payment_link_url = payment_result["payment_link_url"]
        payment_link_id = payment_result["payment_link_id"]

        # Store payment link ID on order
        order.razorpay_payment_link_id = payment_link_id

    except ValueError as e:
        db.rollback()
        logger.error(f"Payment link creation failed: {e}")
        return PlaceOrderResponse(
            success=False,
            message=f"Failed to create payment link: {e}",
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected payment error: {e}")
        return PlaceOrderResponse(
            success=False,
            message="Payment service unavailable. Please try again.",
        )

    # ── Clear the cart ──
    db.delete(cart)

    # ── Log SMS Replacement ──
    # SMS disabled; Rightside / WhatsApp integration will handle links if needed in future
    logger.info(f"Payment link for Order {order_id} generated: {payment_link_url}")

    # ── Commit everything ──
    db.commit()

    logger.info(
        f"Order {order_id} created successfully. "
        f"Total: ₹{total_amount}, Payment link: {payment_link_url}"
    )

    return PlaceOrderResponse(
        success=True,
        message=f"Order {order_id} placed! Please complete payment.",
        order_id=order_id,
        total_amount=total_amount,
        payment_link=payment_link_url,
        items=order_item_schemas,
    )
