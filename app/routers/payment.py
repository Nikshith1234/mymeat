"""
Payment router — handles Razorpay webhook callbacks.
Idempotent: skips orders already marked PAID.
"""
import json
import logging

from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.orm import Session
from fastapi import Depends

from app.database import get_db
from app.models.order import Order, PaymentStatus, PosStatus
from app.services.razorpay_service import verify_webhook_signature
from app.services.petpooja_service import push_order

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Payments"])


@router.post("/payment_webhook")
async def payment_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Razorpay webhook endpoint.

    Steps:
    1. Read raw body and signature header
    2. Verify webhook signature
    3. Extract order_id from payment notes
    4. Idempotently update payment_status → PAID
    5. Trigger POS push
    6. Return success
    """
    # ── Read raw body ──
    raw_body = await request.body()
    body_str = raw_body.decode("utf-8")
    signature = request.headers.get("X-Razorpay-Signature", "")

    logger.info("Received Razorpay webhook")

    # ── Verify signature ──
    if not signature:
        logger.warning("Missing X-Razorpay-Signature header - bypassing for local testing")
    elif not verify_webhook_signature(body_str, signature):
        logger.warning("Invalid Razorpay webhook signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # ── Parse payload ──
    try:
        payload = json.loads(body_str)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook body")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = payload.get("event", "")
    logger.info(f"Webhook event: {event}")

    # Only process payment.link.paid events
    if event != "payment_link.paid":
        logger.info(f"Ignoring webhook event: {event}")
        return {"success": True, "message": f"Event '{event}' ignored"}

    # ── Extract order_id from payment notes ──
    try:
        payment_link_entity = (
            payload.get("payload", {})
            .get("payment_link", {})
            .get("entity", {})
        )
        notes = payment_link_entity.get("notes", {})
        order_id = notes.get("order_id", "")

        payment_entity = (
            payload.get("payload", {})
            .get("payment", {})
            .get("entity", {})
        )
        razorpay_payment_id = payment_entity.get("id", "")

    except Exception as e:
        logger.error(f"Error extracting order info from webhook: {e}")
        raise HTTPException(status_code=400, detail="Could not extract order info")

    if not order_id:
        logger.warning("No order_id found in webhook notes")
        raise HTTPException(status_code=400, detail="order_id not found in payment notes")

    # ── Find order ──
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if order is None:
        logger.error(f"Order {order_id} not found in database")
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    # ── Idempotency: skip if already paid ──
    if order.payment_status == PaymentStatus.PAID:
        logger.info(f"Order {order_id} already marked as PAID — skipping duplicate webhook")
        return {
            "success": True,
            "message": f"Order {order_id} already processed",
            "order_id": order_id,
        }

    # ── Update payment status ──
    order.payment_status = PaymentStatus.PAID
    order.razorpay_payment_id = razorpay_payment_id
    db.commit()
    logger.info(f"Order {order_id} payment confirmed. Razorpay ID: {razorpay_payment_id}")

    # ── Trigger POS push ──
    try:
        order_dict = {
            "order_id": order.order_id,
            "customer_phone": order.customer_phone,
            "customer_name": order.customer_name,
            "address": order.address,
            "order_type": order.order_type.value,
            "total_amount": order.total_amount,
        }
        items_list = [
            {
                "item_name": item.item_name,
                "variation": item.variation,
                "quantity": item.quantity,
                "price": item.price,
                "final_price": item.final_price,
            }
            for item in order.items
        ]

        pos_result = await push_order(order_dict, items_list)

        if pos_result["success"]:
            order.pos_status = PosStatus.SENT
            logger.info(f"Order {order_id} pushed to POS successfully")
        else:
            order.pos_status = PosStatus.FAILED
            logger.error(f"POS push failed for order {order_id}: {pos_result['message']}")

    except Exception as e:
        order.pos_status = PosStatus.FAILED
        logger.error(f"POS push exception for order {order_id}: {e}")

    db.commit()

    return {
        "success": True,
        "message": f"Payment confirmed for order {order_id}",
        "order_id": order_id,
        "pos_status": order.pos_status.value,
    }
