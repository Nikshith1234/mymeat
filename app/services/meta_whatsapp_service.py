"""
Meta WhatsApp Business API Service
Handles sending WhatsApp messages via Meta's official API using verified templates.
"""
import logging
import httpx
from app.config import get_settings
from app.services.twilio_service import NOTIFY_NUMBER

logger = logging.getLogger(__name__)

# Note: Replaced hardcoded values with dynamic env variables via get_settings()
def send_order_confirmation(customer_phone: str, order_id: str) -> bool:
    """
    Send an order confirmation message using the verified Meta WhatsApp template
    `meatcraft_order_confirmation`.

    Args:
        customer_phone: Customer's phone number (starting with 91, e.g. 919876543210).
        order_id: The order ID to include in the template.

    Returns:
        True if the message was sent successfully, False otherwise.
    """
    # Note: Hardcoded to NOTIFY_NUMBER for testing instead of customer_phone
    # Ensure the phone number doesn't have a leading '+'
    to = NOTIFY_NUMBER.lstrip("+")

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": "meatcraft_order_confirmation",
            "language": {
                "code": "en"
            },
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": order_id
                        }
                    ]
                }
            ]
        }
    }

    settings = get_settings()
    
    # Don't fail if secrets missing, just log
    if not settings.META_PHONE_NUMBER_ID or not settings.META_ACCESS_TOKEN:
        logger.error("[META WA] Missing META_PHONE_NUMBER_ID or META_ACCESS_TOKEN in env")
        return False
        
    meta_api_url = f"https://graph.facebook.com/v17.0/{settings.META_PHONE_NUMBER_ID}/messages"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.META_ACCESS_TOKEN}"
    }

    try:
        response = httpx.post(meta_api_url, json=payload, headers=headers, timeout=15.0)
        if response.status_code == 200:
            logger.info(f"[META WA] Order confirmation sent to {to} for order {order_id}")
            return True
        else:
            logger.error(f"[META WA] Failed to send message. Status: {response.status_code}, Body: {response.text}")
            return False
    except Exception as e:
        logger.error(f"[META WA] Exception while sending message: {e}")
        return False
