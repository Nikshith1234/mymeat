"""
Order router — handles order placement from cart.
"""
import logging
from typing import List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.database import get_db
from app.models.pydantic_models import OrderType, PaymentStatus, PosStatus, KitchenStatus, MongoOrder, MongoOrderItem
from app.schemas.order_schema import PlaceOrderRequest, PlaceOrderResponse, OrderSchema
from app.schemas.cart_schema import CartItemSchema
from app.utils.id_generator import generate_order_id
from app.services.razorpay_service import create_payment_link
from app.services.petpooja_service import send_to_petpooja
from app.services.meta_whatsapp_service import send_order_confirmation, send_payment_link_message
from app.routers.cart import _resolve_session


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Orders"])

@router.post("/place_order", response_model=PlaceOrderResponse)
async def place_order(
    request: PlaceOrderRequest,
    raw_request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Place an order from the current cart.
    Instantly confirms the order (PENDING). Payment link is generated when Processed.
    """
    customer_phone = request.caller_number or request.customer_phone or ""
    logger.info(f"[CALLER] place_order phone={customer_phone!r}")

    session_key = _resolve_session(raw_request, request.caller_number, request.session_id)
    logger.info(f"[ORDER] place_order session_key={session_key!r}, phone={customer_phone!r}")

    print(f"\n==============================================")
    print(f"📞 Riya CALLED: PLACE ORDER")
    print(f"📞 SESSION KEY: {session_key}")
    print(f"📞 CUSTOMER PHONE: {customer_phone}")
    print(f"==============================================\n")

    order_type_upper = request.order_type.upper()
    if order_type_upper not in ("DELIVERY", "PICKUP"):
        return PlaceOrderResponse(
            success=False,
            message="Invalid order_type. Must be DELIVERY or PICKUP.",
        )

    if order_type_upper == "DELIVERY" and not request.address:
        return PlaceOrderResponse(
            success=False,
            message="Address is required for DELIVERY orders.",
        )

    # Get cart
    cart = await db["carts"].find_one({"session_id": session_key})
    if cart is None or not cart.get("items"):
        return PlaceOrderResponse(
            success=False,
            message=f"Cart is empty (session: {session_key!r}). Add items before placing an order.",
        )

    cart_items = cart["items"]
    total_amount = cart.get("total_amount", 0.0)

    # Generate unique order ID
    order_id = generate_order_id()
    while await db["orders"].find_one({"order_id": order_id}) is not None:
        order_id = generate_order_id()

    # Create OrderItem records
    mongo_items = []
    order_item_schemas = []
    for item in cart_items:
        mongo_items.append(MongoOrderItem(**item))
        order_item_schemas.append(CartItemSchema(**item))

    # Create Order record
    order = MongoOrder(
        order_id=order_id,
        customer_phone=customer_phone,
        customer_name=request.customer_name,
        address=request.address,
        order_type=OrderType(order_type_upper),
        arrival_time=request.arrival_time,
        total_amount=total_amount,
        payment_status=PaymentStatus.PENDING,
        pos_status=PosStatus.NOT_SENT,
        kitchen_status=KitchenStatus.PENDING,
        items=mongo_items,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    
    order_dict = order.model_dump()
    await db["orders"].insert_one(order_dict)

    # Clear the cart
    await db["carts"].delete_one({"session_id": session_key})

    logger.info(f"Order {order_id} created successfully. Total: ₹{total_amount}")

    # Send WhatsApp notification via Meta API (verified template)
    send_order_confirmation(customer_phone, order_id)

    # Send to PetPooja POS (can be async or sync depending on implementation)
    try:
        class DummyOrderObj: pass
        dummy_order = DummyOrderObj()
        for k, v in order_dict.items():
            setattr(dummy_order, k, v)
        
        class DummyItemObj: pass
        dummy_items = []
        for i in mongo_items:
            d_i = DummyItemObj()
            for k, v in i.model_dump().items():
                setattr(d_i, k, v)
            dummy_items.append(d_i)

        success = await send_to_petpooja(dummy_order, dummy_items)
        if success:
            await db["orders"].update_one(
                {"order_id": order_id},
                {"$set": {"pos_status": PosStatus.SENT.value}}
            )
    except Exception as e:
        logger.error(f"PetPooja send failed for {order_id}: {e}")
        await db["orders"].update_one({"order_id": order_id}, {"$set": {"pos_status": PosStatus.FAILED.value}})

    return PlaceOrderResponse(
        success=True,
        message=f"Order {order_id} placed! It will be reviewed by the shop soon.",
        order_id=order_id,
        total_amount=total_amount,
        payment_link="", # Sent later by shop
        items=order_item_schemas,
    )


@router.get("/orders", response_model=List[OrderSchema])
async def get_all_orders(db: AsyncIOMotorDatabase = Depends(get_db)):
    """
    Fetch all placed orders for the frontend dashboard.
    """
    cursor = db["orders"].find()
    db_orders = await cursor.to_list(length=1000)
    
    response_orders = []
    for order in db_orders:
        order_items = []
        for item in order.get("items", []):
            order_items.append(CartItemSchema(**item))
            
        timestamp_str = "Recently"
        if "created_at" in order and order["created_at"]:
            if isinstance(order["created_at"], datetime):
                timestamp_str = order["created_at"].strftime("%I:%M %p")

        order_data = OrderSchema(
            order_id=order.get("order_id"),
            customer_name=order.get("customer_name") or "Unknown",
            customer_phone=order.get("customer_phone"),
            address=order.get("address"),
            order_type=order.get("order_type"),
            payment_status=order.get("payment_status"),
            pos_status=order.get("pos_status"),
            total_amount=order.get("total_amount"),
            status=order.get("kitchen_status"),
            items=order_items,
            timestamp=timestamp_str,
            arrival_time=order.get("arrival_time")
        )
        response_orders.append(order_data)
        
    response_orders.reverse()
    return response_orders


@router.delete("/orders/{order_id}")
async def clear_order(order_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    """
    Permanently delete an order from the database.
    """
    result = await db["orders"].delete_one({"order_id": order_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
        
    return {"success": True, "message": f"Order {order_id} cleared"}


class StatusUpdate(BaseModel):
    status: str

@router.patch("/orders/{order_id}/status")
async def update_order_status(order_id: str, body: StatusUpdate, db: AsyncIOMotorDatabase = Depends(get_db)):
    """
    Update kitchen status of an order.
    """
    try:
        new_status = KitchenStatus(body.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status '{body.status}'.")

    result = await db["orders"].update_one(
        {"order_id": order_id},
        {"$set": {"kitchen_status": new_status.value, "updated_at": datetime.utcnow()}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")

    return {"success": True, "order_id": order_id, "status": new_status.value}


@router.post("/orders/{order_id}/process")
async def process_order(order_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    """
    Process an order: Generate Razorpay link, send SMS (mocked for now), 
    and update status to 'preparing' or some intermediate state.
    """
    order = await db["orders"].find_one({"order_id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    new_status = KitchenStatus.AWAITING_PAYMENT

    if order.get("payment_status") == PaymentStatus.PENDING.value:
        try:
            payment_result = create_payment_link(
                order_id=order_id,
                amount=order.get("total_amount", 0.0),
                customer_phone=order.get("customer_phone", ""),
                customer_name=order.get("customer_name", ""),
            )
            payment_link_url = payment_result["payment_link_url"]
            payment_link_id = payment_result["payment_link_id"]

            await db["orders"].update_one(
                {"order_id": order_id},
                {
                    "$set": {
                        "razorpay_payment_link_id": payment_link_id,
                        "payment_link_url": payment_link_url,
                        "kitchen_status": new_status.value,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            logger.info(f"Generated payment link for {order_id}: {payment_link_url}")
        except Exception as e:
            logger.error(f"Error processing payment link for {order_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to generate payment link.")
            
    else:
        # Just update status if already paid (unlikely in new flow, but safe fallback)
        await db["orders"].update_one(
            {"order_id": order_id},
            {"$set": {"kitchen_status": new_status.value, "updated_at": datetime.utcnow()}}
        )

    updated_order = await db["orders"].find_one({"order_id": order_id})
    payment_link_url = updated_order.get("payment_link_url", "") if updated_order else ""

    return {
        "success": True, 
        "order_id": order_id, 
        "status": new_status.value, 
        "payment_link_url": payment_link_url
    }

@router.post("/orders/{order_id}/send_payment_link")
async def send_payment_link(order_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    """
    Fetch the order's payment link and send it via Twilio WhatsApp.
    """
    order = await db["orders"].find_one({"order_id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    payment_link_url = order.get("payment_link_url")
    if not payment_link_url:
        raise HTTPException(status_code=400, detail="No payment link generated for this order yet.")

    customer_phone = order.get("customer_phone", "")
    success = send_payment_link_message(customer_phone, order_id, payment_link_url)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to send payment link via WhatsApp.")

    return {"success": True, "message": "Payment link sent successfully"}
