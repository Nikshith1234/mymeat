"""
Order router — handles order placement from cart.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cart import Cart
from app.models.order import Order, OrderItem, OrderType, PaymentStatus, PosStatus, KitchenStatus
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
    print(f"\n==============================================")
    print(f"📞 AAKASH CALLED: PLACE ORDER")
    print(f"📞 DETECTED CALLER PHONE: {request.session_id}")
    print(f"==============================================\n")


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
        payment_status=PaymentStatus.PAID,  # Instantly confirm the order for testing
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
        logger.warning(f"Payment link creation failed (Using mock link): {e}")
        payment_link_url = "http://mock-payment-link/for-testing"
    except Exception as e:
        logger.warning(f"Unexpected payment error (Using mock link): {e}")
        payment_link_url = "http://mock-payment-link/for-testing"

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


from typing import List
from app.schemas.order_schema import OrderSchema

@router.get("/orders", response_model=List[OrderSchema])
async def get_all_orders(db: Session = Depends(get_db)):
    """
    Fetch all placed orders for the frontend dashboard.
    Orders are retrieved with their items.
    """
    # Fetch all orders from database 
    db_orders = db.query(Order).all()
    
    response_orders = []
    for order in db_orders:
        
        # Determine internal UI status based on payment/pos state
        # (This can be basic logic, defaults to 'pending')
        status = "pending"
        if order.pos_status == PosStatus.SENT:
            status = "preparing"
        
        # Convert items
        order_items = []
        for item in order.items:
            order_items.append(CartItemSchema(
                item_name=item.item_name,
                variation=item.variation,
                quantity=item.quantity,
                price=item.price,
                final_price=item.final_price
            ))
            
        # Optional: format a simple timestamp string from DB created_at 
        # (Assuming your order model has generic timestamps, if not fallback to None)
        timestamp_str = "Recently"
        if hasattr(order, 'created_at') and order.created_at:
             # Basic time format like '10:15 AM'
             timestamp_str = order.created_at.strftime("%I:%M %p")

        order_data = OrderSchema(
            order_id=order.order_id,
            customer_name=order.customer_name or "Unknown",
            customer_phone=order.customer_phone,
            address=order.address,
            order_type=order.order_type.value if hasattr(order.order_type, 'value') else str(order.order_type),
            payment_status=order.payment_status.value if hasattr(order.payment_status, 'value') else str(order.payment_status),
            pos_status=order.pos_status.value if hasattr(order.pos_status, 'value') else str(order.pos_status),
            total_amount=order.total_amount,
            status=order.kitchen_status.value if hasattr(order.kitchen_status, 'value') else str(order.kitchen_status),
            items=order_items,
            timestamp=timestamp_str
        )
        response_orders.append(order_data)
        
    # Reverse to show newest first
    response_orders.reverse()
    
    return response_orders


@router.delete("/orders/{order_id}")
async def clear_order(order_id: str, db: Session = Depends(get_db)):
    """
    Permanently delete an order from the database (e.g. when cleared from frontend).
    """
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    db.delete(order)
    db.commit()
    return {"success": True, "message": f"Order {order_id} cleared"}


from pydantic import BaseModel

class StatusUpdate(BaseModel):
    status: str

@router.patch("/orders/{order_id}/status")
async def update_order_status(order_id: str, body: StatusUpdate, db: Session = Depends(get_db)):
    """
    Update kitchen status of an order (pending → preparing → ready).
    """
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    try:
        order.kitchen_status = KitchenStatus(body.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status '{body.status}'. Must be pending, preparing, or ready.")

    db.commit()
    return {"success": True, "order_id": order_id, "status": order.kitchen_status.value}
