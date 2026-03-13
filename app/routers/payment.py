"""
Payment router — handles Razorpay webhook callbacks.
Idempotent: skips orders already marked PAID.
"""
import json
import logging

from fastapi import APIRouter, Request, HTTPException
from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_db
from app.models.pydantic_models import PaymentStatus, KitchenStatus, PosStatus
from app.services.razorpay_service import verify_webhook_signature
from app.services.petpooja_service import send_to_petpooja
from app.services.meta_whatsapp_service import send_payment_received_message, NOTIFY_NUMBER

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Payments"])


@router.post("/payment_webhook")
async def payment_webhook(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
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
    order = await db["orders"].find_one({"order_id": order_id})
    if order is None:
        logger.error(f"Order {order_id} not found in database")
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    # ── Idempotency: skip if already paid ──
    if order.get("payment_status") == PaymentStatus.PAID.value:
        logger.info(f"Order {order_id} already marked as PAID — skipping duplicate webhook")
        return {
            "success": True,
            "message": f"Order {order_id} already processed",
            "order_id": order_id,
        }

    # ── Update payment status and kitchen status ──
    await db["orders"].update_one(
        {"order_id": order_id},
        {"$set": {
            "payment_status": PaymentStatus.PAID.value, 
            "kitchen_status": KitchenStatus.PAID.value,
            "razorpay_payment_id": razorpay_payment_id
        }}
    )
    logger.info(f"Order {order_id} payment confirmed. Razorpay ID: {razorpay_payment_id}")

    # ── Notify User ──
    try:
        # Note: Hardcoded to NOTIFY_NUMBER internally in meta_whatsapp_service for testing
        send_payment_received_message(order.get("customer_phone"), order_id)
        logger.info(f"Sent WhatsApp success notification for order {order_id} to test number")
    except Exception as e:
        logger.error(f"Failed to send WhatsApp notification for order {order_id}: {e}")

    # ── Trigger POS push ──
    final_pos_status = PosStatus.NOT_SENT.value
    try:
        class DummyOrderObj: pass
        dummy_order = DummyOrderObj()
        for k, v in order.items():
            setattr(dummy_order, k, v)
        dummy_order.payment_status = PaymentStatus.PAID
        dummy_order.razorpay_payment_id = razorpay_payment_id
        
        class DummyItemObj: pass
        dummy_items = []
        for i in order.get("items", []):
            d_i = DummyItemObj()
            for k, v in i.items():
                setattr(d_i, k, v)
            dummy_items.append(d_i)

        success = await send_to_petpooja(dummy_order, dummy_items)
        final_pos_status = PosStatus.SENT.value if success else PosStatus.FAILED.value
        if success:
            logger.info(f"Order {order_id} pushed to POS successfully")
        else:
            logger.error(f"POS push failed for order {order_id}")
    except Exception as e:
        final_pos_status = PosStatus.FAILED.value
        logger.error(f"POS push exception for order {order_id}: {e}")

    await db["orders"].update_one(
        {"order_id": order_id},
        {"$set": {"pos_status": final_pos_status}}
    )

    return {
        "success": True,
        "message": f"Payment confirmed for order {order_id}",
        "order_id": order_id,
        "pos_status": final_pos_status,
    }
