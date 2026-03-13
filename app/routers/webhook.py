from fastapi import APIRouter, Request, Response
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/whatsapp")
async def twilio_whatsapp_webhook(request: Request):
    """
    Handle incoming WhatsApp messages and status updates from Twilio.
    """
    try:
        form_data = await request.form()
        logger.info(f"[WEBHOOK] Received WhatsApp webhook: {dict(form_data)}")
        
        # Twilio expects a valid TwiML response for incoming messages.
        # An empty <Response></Response> tells Twilio we received it and have no immediate reply.
        return Response(content="<Response></Response>", media_type="application/xml")
    except Exception as e:
        logger.error(f"[WEBHOOK] Error processing WhatsApp webhook: {e}")
        return Response(content="<Response></Response>", media_type="application/xml")
        
from app.services.razorpay_service import verify_webhook_signature
from app.services.meta_whatsapp_service import send_payment_received_message
from app.database import get_db
from app.models.pydantic_models import KitchenStatus, PaymentStatus
from fastapi import Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
import json

@router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    Handle incoming webhooks from Razorpay for payment success.
    """
    payload_body = await request.body()
    signature = request.headers.get("x-razorpay-signature")

    is_valid = verify_webhook_signature(payload_body.decode("utf-8"), signature)
    if not is_valid:
        logger.error("[WEBHOOK] Invalid Razorpay signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        data = json.loads(payload_body)
        event = data.get("event")

        if event == "payment_link.paid":
            payment_link_id = data["payload"]["payment_link"]["entity"]["id"]
            
            # Find the order
            order = await db["orders"].find_one({"razorpay_payment_link_id": payment_link_id})
            if order:
                order_id = order["order_id"]
                customer_phone = order.get("customer_phone")
                
                # Update status
                await db["orders"].update_one(
                    {"order_id": order_id},
                    {"$set": {
                        "payment_status": PaymentStatus.PAID.value,
                        "kitchen_status": KitchenStatus.PAID.value
                    }}
                )
                logger.info(f"[WEBHOOK] Order {order_id} marked as PAID via Razorpay webhook.")
                
                # Notify User
                if customer_phone:
                    send_payment_received_message(customer_phone, order_id)
            else:
                logger.warning(f"[WEBHOOK] Received payment_link.paid but no order found for link id: {payment_link_id}")

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"[WEBHOOK] Error processing Razorpay webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
