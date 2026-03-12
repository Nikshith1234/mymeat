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

from app.services.menu_service import get_menu


async def build_petpooja_payload(order, order_items: list) -> dict:
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

    # Dynamic prep time based on total amount
    total_amt = float(order.total_amount)
    if total_amt > 1000:
        min_prep_time = 45
    elif total_amt > 500:
        min_prep_time = 30
    else:
        min_prep_time = 20

    menu_data = await get_menu()
    items_list = menu_data.get("items", [])
    taxes_list = menu_data.get("taxes", [])
    taxes_lookup = {str(t.get("taxid", "")): t for t in taxes_list}

    petpooja_items = []
    tax_details_dict = {}

    for item in order_items:
        # 1. Match item by name
        matched_item = None
        for mi in items_list:
            if mi.get("itemname", "").lower() == item.item_name.lower():
                matched_item = mi
                break

        if not matched_item:
            # Try fuzzy match
            for mi in items_list:
                name = mi.get("itemname", "")
                if item.item_name.lower() in name.lower() or name.lower() in item.item_name.lower():
                    matched_item = mi
                    break
        
        if not matched_item:
            logger.warning(f"Item not found in menu for PetPooja payload: {item.item_name}")
            # Fallback for missing items
            matched_item = {
                "itemid": "0000",
                "itemname": item.item_name,
                "tax_inclusive": False,
                "gst_liability": "restaurant",
                "item_tax": ""
            }

        # 2. Match variation
        matched_var = None
        variation_name = ""
        variation_id = ""
        variations = matched_item.get("variation", [])
        
        if item.variation and variations:
            for v in variations:
                if v.get("name", "").replace(" ", "").lower() == item.variation.replace(" ", "").lower():
                    matched_var = v
                    break
        
        if matched_var:
            variation_id = matched_var.get("id", "")
            variation_name = matched_var.get("name", "")

        # 3. Handle taxes
        item_taxes = []
        item_tax_str = matched_item.get("item_tax", "")
        tax_ids = [tid.strip() for tid in item_tax_str.split(',')] if item_tax_str else []
        
        gross_amount = float(item.price) * int(item.quantity)
        
        for tid in tax_ids:
            if tid in taxes_lookup:
                tax_info = taxes_lookup[tid]
                tax_pct = float(tax_info.get("tax", 0))
                
                if matched_item.get("tax_inclusive", False):
                    tax_amt = gross_amount - (gross_amount / (1 + (tax_pct / 100)))
                else:
                    tax_amt = gross_amount * (tax_pct / 100)
                
                tax_amt = round(tax_amt, 2)
                item_taxes.append({
                    "id": tid,
                    "name": tax_info.get("taxname", ""),
                    "tax_percentage": str(tax_pct),
                    "amount": tax_amt
                })
                
                if tid in tax_details_dict:
                    tax_details_dict[tid]["tax"] += tax_amt
                    tax_details_dict[tid]["tax"] = round(tax_details_dict[tid]["tax"], 2)
                    tax_details_dict[tid]["restaurant_liable_amt"] = round(tax_details_dict[tid]["tax"], 2)
                else:
                    tax_details_dict[tid] = {
                        "id": tid,
                        "title": tax_info.get("taxname", ""),
                        "type": order_type_code,
                        "price": tax_pct,
                        "tax": tax_amt,
                        "restaurant_liable_amt": tax_amt
                    }

        petpooja_items.append({
            "id": matched_item.get("itemid", ""),
            "name": matched_item.get("itemname", item.item_name),
            "price": f"{item.price:.2f}",
            "item_discount": "0",
            "final_price": f"{item.final_price:.2f}",
            "quantity": str(item.quantity),
            "description": matched_item.get("itemdescription", ""),
            "variation_name": variation_name,
            "variation_id": variation_id,
            "tax_inclusive": matched_item.get("tax_inclusive", False),
            "gst_liability": matched_item.get("gst_liability", "restaurant"),
            "item_tax": item_taxes,
            "AddonItem": {"details": []}
        })

    tax_details = list(tax_details_dict.values())
    tax_total = sum(float(t["tax"]) for t in tax_details)

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
                        "email":     "dummy.email@test.com",
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
                        "tax_total":        f"{tax_total:.2f}",
                        "total":            f"{order.total_amount:.2f}",
                        "description":      "",
                        "created_on":       now_ist.strftime("%Y-%m-%d %H:%M:%S"),
                        "enable_delivery":  1,
                        "min_prep_time":    min_prep_time,
                        "callback_url":     "NA",
                        "collect_cash":     "0",
                        "otp":              "",
                    }
                },
                "OrderItem": {"details": petpooja_items},
                "Tax":       {"details": tax_details},
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
    payload = await build_petpooja_payload(order, order_items)
    logger.info(f"Sending order {order.order_id} to PetPooja...")
    
    # Print the payload to the terminal so the user can see it each time
    print(f"\n{'='*50}\nPETPOOJA PAYLOAD FOR ORDER {order.order_id}:\n{json.dumps(payload, indent=2)}\n{'='*50}\n")
    
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
