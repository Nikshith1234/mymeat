"""
Twilio WhatsApp Service
Handles sending WhatsApp messages via Twilio.
"""
import logging
from twilio.rest import Client
from app.config import get_settings

logger = logging.getLogger(__name__)

# Fixed recipient number for Meatcraft notifications
NOTIFY_NUMBER = "+919071584924"


def send_whatsapp_message(message: str, to: str = NOTIFY_NUMBER) -> bool:
    """
    Send a WhatsApp message via Twilio.

    Args:
        message: The text message to send.
        to: Recipient WhatsApp number (defaults to shop owner: +919071584924).

    Returns:
        True if sent successfully, False otherwise.
    """
    settings = get_settings()

    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.error("[TWILIO] Missing TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN in environment.")
        return False

    if not settings.TWILIO_WHATSAPP_FROM:
        logger.error("[TWILIO] Missing TWILIO_WHATSAPP_FROM in environment.")
        return False

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        msg = client.messages.create(
            from_=f"whatsapp:{settings.TWILIO_WHATSAPP_FROM}",
            to=f"whatsapp:{to}",
            body=message,
        )

        logger.info(f"[TWILIO] WhatsApp message sent. SID: {msg.sid}, To: {to}")
        return True

    except Exception as e:
        logger.error(f"[TWILIO] Failed to send WhatsApp message: {e}")
        return False


def notify_new_order(order_id: str, customer_name: str, customer_phone: str,
                     order_type: str, total: float, items_summary: str) -> bool:
    """
    Notify the shop owner about a new order via WhatsApp.
    """
    message = (
        f"🛒 *New Meatcraft Order*\n\n"
        f"📋 Order ID: {order_id}\n"
        f"👤 Customer: {customer_name}\n"
        f"📞 Phone: {customer_phone}\n"
        f"🚚 Type: {order_type}\n"
        f"🧾 Items:\n{items_summary}\n"
        f"💰 Total: ₹{total:.0f}"
    )
    return send_whatsapp_message(message)


def notify_order_placed(customer_phone: str) -> bool:
    """
    Notify user that order is placed and waiting for butcher.
    """
    message = "order placed waiting for the butcher to process your req."
    return send_whatsapp_message(message, to=NOTIFY_NUMBER)


def notify_payment_link(customer_phone: str, payment_link: str) -> bool:
    """
    Notify user to confirm order by payment with the link.
    """
    message = f"confirm order by payment. Link: {payment_link}"
    return send_whatsapp_message(message, to=NOTIFY_NUMBER)
