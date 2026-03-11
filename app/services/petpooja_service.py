"""
PetPooja POS Integration Service.

Sends confirmed Meatcraft orders to PetPooja's save_order API so they
appear as Kitchen Order Tickets (KOTs) in the POS system automatically.

HOW TO CONFIGURE (mentor will provide values):
----------------------------------------------
Add to .env:
    PETPOOJA_APP_KEY=<from PetPooja dashboard>
    PETPOOJA_APP_SECRET=<from PetPooja dashboard>
    PETPOOJA_ACCESS_TOKEN=<from PetPooja dashboard>
    PETPOOJA_RESTAURANT_ID=<your restID>
    PETPOOJA_RESTAURANT_NAME=Meatcraft

Then fill in ITEM_ID_MAP below with PetPooja item IDs.
Get IDs from PetPooja dashboard → Menu → each item.
Replace all "FILL_IN" strings with real numeric IDs.
"""

import json
import logging
import httpx
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
from app.config import get_settings

logger = logging.getLogger(__name__)

PETPOOJA_SAVE_ORDER_URL = "https://pponlineordercb.petpooja.com/save_order"
# IST initialized above

# ─────────────────────────────────────────────────────────────────────────────
# ITEM ID MAP  ← Mentor: replace every "FILL_IN" with PetPooja item ID
# Key format:  "Item Name (Variation)"  or  "Item Name"  (if no variation)
# ─────────────────────────────────────────────────────────────────────────────
ITEM_ID_MAP: dict = {
    # ── Chicken ──
    "Chicken Curry Cut (250 Grms)":                "FILL_IN",
    "Chicken Curry Cut (1 Kg)":                    "FILL_IN",
    "Chicken Boneless Breast (250 Grms)":          "FILL_IN",
    "Chicken Boneless Breast (500 Grms)":          "FILL_IN",
    "Chicken Boneless Breast (750 Grms)":          "FILL_IN",
    "Chicken Boneless Breast (1 Kg)":              "FILL_IN",
    "Chicken Thigh Boneless (250 Grms)":           "FILL_IN",
    "Chicken Thigh Boneless (500 Grms)":           "FILL_IN",
    "Chicken Thigh Boneless (750 Grms)":           "FILL_IN",
    "Chicken Thigh Boneless (1 Kg)":               "FILL_IN",
    "Chicken Wings (250 Grms)":                    "FILL_IN",
    "Chicken Wings (500 Grms)":                    "FILL_IN",
    "Chicken Wings (750 Grms)":                    "FILL_IN",
    "Chicken Wings (1 Kg)":                        "FILL_IN",
    "Chicken Kalmi (250 Grms)":                    "FILL_IN",
    "Chicken Kalmi (500 Grms)":                    "FILL_IN",
    "Chicken Kalmi (750 Grms)":                    "FILL_IN",
    "Chicken Kalmi (1 Kg)":                        "FILL_IN",
    "Chicken Tangri (250 Grms)":                   "FILL_IN",
    "Chicken Tangri (500 Grms)":                   "FILL_IN",
    "Chicken Tangri (750 Grms)":                   "FILL_IN",
    "Chicken Tangri (1 Kg)":                       "FILL_IN",
    "Chicken Full Leg (250 Grms)":                 "FILL_IN",
    "Chicken Full Leg (500 Grms)":                 "FILL_IN",
    "Chicken Full Leg (1 Kg)":                     "FILL_IN",
    "Chicken Keema (250 Grms)":                    "FILL_IN",
    "Chicken Keema (500 Grms)":                    "FILL_IN",
    "Chicken Keema (1 Kg)":                        "FILL_IN",
    "Chicken Liver (1 Kg)":                        "FILL_IN",
    "Regular Chicken (1 Kg)":                      "FILL_IN",
    "Chicken Broiler (Pcs)":                       "FILL_IN",
    "Chicken Lollipop (500 Grms)":                 "FILL_IN",
    "Chicken Lollipop (1 Kg)":                     "FILL_IN",
    "Chicken Bones (1 Kg)":                        "FILL_IN",
    "Chicken Boneless Breast With Wings (1 Kg)":   "FILL_IN",
    "Chicken Breast With Bone (1 Kg)":             "FILL_IN",
    # ── Mutton ──
    "Mutton Curry Cut (250 Grms)":                 "FILL_IN",
    "Mutton Curry Cut (500 Grms)":                 "FILL_IN",
    "Mutton Curry Cut (750 Grms)":                 "FILL_IN",
    "Mutton Curry Cut (1 Kg)":                     "FILL_IN",
    "Mutton Boneless (250 Grms)":                  "FILL_IN",
    "Mutton Boneless (1 Kg)":                      "FILL_IN",
    "Mutton Keema (250 Grms)":                     "FILL_IN",
    "Mutton Keema (500 Grms)":                     "FILL_IN",
    "Mutton Keema (750 Grms)":                     "FILL_IN",
    "Mutton Keema (1 Kg)":                         "FILL_IN",
    "Mutton Chop (250 Grms)":                      "FILL_IN",
    "Mutton Chop (500 Grms)":                      "FILL_IN",
    "Mutton Chop (750 Grms)":                      "FILL_IN",
    "Mutton Chop (1 Kg)":                          "FILL_IN",
    "Mutton Nali (250 Grms)":                      "FILL_IN",
    "Mutton Nali (500 Grms)":                      "FILL_IN",
    "Mutton Nali (750 Grms)":                      "FILL_IN",
    "Mutton Nali (1 Kg)":                          "FILL_IN",
    "Mutton Barra (250 Grms)":                     "FILL_IN",
    "Mutton Barra (500 Grms)":                     "FILL_IN",
    "Mutton Barra (750 Grms)":                     "FILL_IN",
    "Mutton Barra (1 Kg)":                         "FILL_IN",
    "Mutton Leg (250 Grms)":                       "FILL_IN",
    "Mutton Leg (500 Grms)":                       "FILL_IN",
    "Mutton Leg (750 Grms)":                       "FILL_IN",
    "Mutton Leg (1 Kg)":                           "FILL_IN",
    "Mutton Liver (250 Grms)":                     "FILL_IN",
    "Mutton Liver (500 Grms)":                     "FILL_IN",
    "Mutton Liver (750 Grms)":                     "FILL_IN",
    "Mutton Liver (1 Kg)":                         "FILL_IN",
    "Mutton Gurde Kapoore (250 Grms)":             "FILL_IN",
    "Mutton Gurde Kapoore (500 Grms)":             "FILL_IN",
    "Mutton Gurde Kapoore (750 Grms)":             "FILL_IN",
    "Mutton Gurde Kapoore (1 Kg)":                 "FILL_IN",
    "Mutton Bone (1 Kg)":                          "FILL_IN",
    "Mutton Head Cut (1 Kg)":                      "FILL_IN",
    "Mutton Fat (1 Kg)":                           "FILL_IN",
    "Roasted Paya (1 Kg)":                         "FILL_IN",
    "Goat Brain (1 Kg)":                           "FILL_IN",
    "Lamb Shank (1 Kg)":                           "FILL_IN",
    # ── Sea Food ──
    "Fish Basa Imported (1 Kg)":                   "FILL_IN",
    "Fish Surmai Boneless (250 Grms)":             "FILL_IN",
    "Fish Surmai Boneless (500 Grms)":             "FILL_IN",
    "Fish Surmai Boneless (750 Grms)":             "FILL_IN",
    "Fish Surmai Boneless (1 Kg)":                 "FILL_IN",
    "Fish River Sole Boneless (250 Grms)":         "FILL_IN",
    "Fish River Sole Boneless (500 Grms)":         "FILL_IN",
    "Fish River Sole Boneless (750 Grms)":         "FILL_IN",
    "Fish River Sole Boneless (1 Kg)":             "FILL_IN",
    "Fish Singhara Boneless (250 Grms)":           "FILL_IN",
    "Fish Singhara Boneless (500 Grms)":           "FILL_IN",
    "Fish Singhara Boneless (750 Grms)":           "FILL_IN",
    "Fish Singhara Boneless (1 Kg)":               "FILL_IN",
}


def _get_item_id(item_name: str, variation: str | None) -> str:
    """Return PetPooja item ID for an item+variation combo."""
    key = f"{item_name} ({variation})" if variation else item_name
    item_id = ITEM_ID_MAP.get(key, "FILL_IN")
    if item_id == "FILL_IN":
        logger.warning(f"PetPooja item ID not mapped for: '{key}'")
    return item_id


def build_petpooja_payload(order, order_items: list) -> dict:
    """
    Build the PetPooja save_order JSON payload from an Order and its items.
    Credentials are read from the .env file via settings.
    """
    settings = get_settings()
    now_ist = datetime.now(IST)

    order_type_code = (
        "P" if str(order.order_type).upper() in ("PICKUP", "ORDERTYPE.PICKUP")
        else "D"
    )

    # Build items list in PetPooja format
    petpooja_items = []
    for item in order_items:
        item_id = _get_item_id(item.item_name, item.variation)
        full_name = f"{item.item_name} {item.variation}" if item.variation else item.item_name
        petpooja_items.append({
            "id": item_id,
            "name": full_name,
            "price": f"{item.price:.2f}",
            "item_discount": "0",
            "final_price": f"{item.final_price:.2f}",
            "quantity": str(item.quantity),
            "description": "",
            "variation_name": item.variation or "",
            "variation_id": "",
            "tax_inclusive": False,
            "gst_liability": "restaurant",
            "item_tax": [],
            "AddonItem": {"details": []},
        })

    # Strip + from phone for PetPooja
    phone = str(order.customer_phone or "").replace("+", "").strip()

    return {
        "app_key":      settings.PETPOOJA_APP_KEY,
        "app_secret":   settings.PETPOOJA_APP_SECRET,
        "access_token": settings.PETPOOJA_ACCESS_TOKEN,
        "orderinfo": {
            "OrderInfo": {
                "Restaurant": {
                    "details": {
                        "res_name":            settings.PETPOOJA_RESTAURANT_NAME,
                        "address":             "NA",
                        "contact_information": "NA",
                        "restID":              settings.PETPOOJA_RESTAURANT_ID,
                    }
                },
                "Customer": {
                    "details": {
                        "email":     "ai.agent@meatcraft.com",
                        "name":      order.customer_name or "NA",
                        "address":   order.address or "NA",
                        "phone":     phone,
                        "latitude":  "NA",
                        "longitude": "NA",
                    }
                },
                "Order": {
                    "details": {
                        "orderID":          order.order_id,
                        "preorder_date":    now_ist.strftime("%Y-%m-%d"),
                        "preorder_time":    now_ist.strftime("%H:%M:%S"),
                        "service_charge":   "0",
                        "sc_tax_amount":    "0",
                        "delivery_charges": "0",
                        "dc_tax_percentage":"0",
                        "dc_tax_amount":    "0",
                        "packing_charges":  "0",
                        "pc_tax_percentage":"0",
                        "pc_tax_amount":    "0",
                        "order_type":       order_type_code,
                        "advanced_order":   "N",
                        "urgent_order":     False,
                        "urgent_time":      0,
                        "payment_type":     "ONLINE",
                        "discount_total":   "0",
                        "discount_type":    "F",
                        "tax_total":        "0.00",
                        "total":            f"{order.total_amount:.2f}",
                        "description":      "",
                        "created_on":       now_ist.strftime("%Y-%m-%d %H:%M:%S"),
                        "enable_delivery":  1,
                        "min_prep_time":    20,
                        "callback_url":     "NA",
                        "collect_cash":     "0",
                        "otp":              "",
                    }
                },
                "OrderItem": {"details": petpooja_items},
                "Tax":       {"details": []},
            }
        },
        "udid":        "",
        "device_type": "agent",
    }


async def send_to_petpooja(order, order_items: list) -> bool:
    """
    POST the order to PetPooja save_order API.
    Returns True on success, False on failure.
    order.pos_status is updated by the caller (order.py).
    """
    payload = build_petpooja_payload(order, order_items)
    logger.info(f"Sending order {order.order_id} to PetPooja...")
    logger.info(f"PetPooja payload:\n{json.dumps(payload, indent=2)}")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                PETPOOJA_SAVE_ORDER_URL,
                headers={"Content-Type": "application/json"},
                json=payload,
            )

        logger.info(f"PetPooja [{response.status_code}]: {response.text[:300]}")

        if response.status_code == 200:
            data = response.json()
            # PetPooja returns {"status": 1, "message": "..."} on success
            if str(data.get("status")) == "1":
                logger.info(f"Order {order.order_id} accepted by PetPooja ✅")
                return True
            logger.warning(f"PetPooja rejected order {order.order_id}: {data}")
            return False

        logger.error(f"PetPooja HTTP {response.status_code}: {response.text[:300]}")
        return False

    except Exception as e:
        logger.error(f"PetPooja request failed for {order.order_id}: {e}")
        return False
