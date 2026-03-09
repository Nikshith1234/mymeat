"""
Rightside / Rock8 Voice service — configures inbound phone number via
https://voice.rock8.ai/inbound/configure

Only phone_number and system_prompt are required.
Tools, voice, language, and provider configs are optional (smart defaults).
"""
import os
import re
import logging
import httpx
import datetime
from typing import Dict, Any, List
from pathlib import Path

class SafeDict(dict):
    def __missing__(self, key):
        return '{' + key + '}'
from app.config import get_settings
from app.services.menu_service import get_menu

logger = logging.getLogger(__name__)

# NOTE: Do NOT cache settings at module level — always call get_settings() inside
# functions so that .env changes take effect after a server restart.


def _update_env_value(key: str, value: str) -> None:
    """Write/update a key=value line in the .env file."""
    env_path = Path(".env")
    if not env_path.exists():
        logger.warning(".env file not found, cannot persist %s", key)
        return
    content = env_path.read_text(encoding="utf-8")
    pattern = rf"^{re.escape(key)}=.*$"
    new_line = f"{key}={value}"
    if re.search(pattern, content, flags=re.MULTILINE):
        content = re.sub(pattern, new_line, content, flags=re.MULTILINE)
    else:
        content = content.rstrip("\n") + f"\n{new_line}\n"
    env_path.write_text(content, encoding="utf-8")
    logger.info("Updated .env: %s", new_line)


async def get_formatted_menu_summary() -> str:
    """
    Compact menu for the system prompt — grouped by category, names only.
    Prices and stock are validated by the backend on add_to_cart.
    """
    try:
        menu_data = await get_menu()
        categories = menu_data.get("categories", [])
        items = menu_data.get("items", [])

        cat_map = {c.get("categoryid"): c.get("categoryname") for c in categories}
        groups: dict = {}

        for item in items:
            if item.get("active") != "1":
                continue
            if item.get("in_stock") != "2":
                continue
            cat_id = item.get("item_categoryid", "")
            cat_name = cat_map.get(cat_id, "Other")
            name = item.get("itemname", "")
            
            variations = item.get("variation", [])
            if variations:
                var_names = [v.get("name", "") for v in variations if v.get("name")]
                if var_names:
                    name = f"{name} (Sizes: {', '.join(var_names)})"

            if name:
                groups.setdefault(cat_name, []).append(name)

        return "\n".join(
            f"{cat}: {', '.join(names)}"
            for cat, names in groups.items()
        )
    except Exception as e:
        logger.error(f"Failed to format menu: {e}")
        return "Menu unavailable."


def get_tool_definitions(base_url: str) -> List[Dict[str, Any]]:
    """
    Define tools in Rock8 format.
    Each parameter MUST have: name, type, description, location, required
    location can be: "body", "query", or "header"
    """
    return [
        {
            "name": "add_to_cart",
            "description": "Add an item to the shopping cart. Call IMMEDIATELY when customer confirms an item. One call per item.",
            "method": "POST",
            "url": f"{base_url}/api/add_to_cart",
            "headers": {},
            "parameters": [
                {"name": "session_id", "type": "string", "description": "Caller phone number exactly as in CALLER PHONE field.", "location": "body", "required": True},
                {"name": "item_name", "type": "string", "description": "Exact name of the menu item as listed in the menu including any typos e.g. Mnutton Bone, Muttom Leg, Regular Chcicken, Fish Surmai Boneleess, FISH SINGHARA BONELESS.", "location": "body", "required": True},
                {"name": "variation", "type": "string", "description": "Item variation e.g. 250 Grms, 500 Grms, 750 Grms, 1 Kg, Pcs. Omit only if item has no variation.", "location": "body", "required": False},
                {"name": "quantity", "type": "integer", "description": "Number of units. Default is 1.", "location": "body", "required": False}
            ]
        },
        {
            "name": "remove_from_cart",
            "description": "Remove a specific item from cart when customer asks to cancel or remove.",
            "method": "POST",
            "url": f"{base_url}/api/remove_from_cart",
            "headers": {},
            "parameters": [
                {"name": "session_id", "type": "string", "description": "Caller phone number. Must match value used in add_to_cart.", "location": "body", "required": True},
                {"name": "item_name", "type": "string", "description": "Exact name of the menu item to remove including any DB typos.", "location": "body", "required": True},
                {"name": "variation", "type": "string", "description": "Variation of item to remove if applicable.", "location": "body", "required": False}
            ]
        },
        {
            "name": "calculate_total",
            "description": "Get all items in cart and total price. Call after customer says done ordering.",
            "method": "POST",
            "url": f"{base_url}/api/calculate_total",
            "headers": {},
            "parameters": [
                {"name": "session_id", "type": "string", "description": "Caller phone number. Must match value used in add_to_cart.", "location": "body", "required": True}
            ]
        },
        {
            "name": "place_order",
            "description": "Place final confirmed order. Call ONLY after items, total, delivery method and name all confirmed.",
            "method": "POST",
            "url": f"{base_url}/api/place_order",
            "headers": {},
            "parameters": [
                {"name": "session_id", "type": "string", "description": "Caller phone number. Must match value used in add_to_cart.", "location": "body", "required": True},
                {"name": "customer_phone", "type": "string", "description": "Caller phone number same as session_id.", "location": "body", "required": True},
                {"name": "customer_name", "type": "string", "description": "Customer name collected at start of call in Step 1.", "location": "body", "required": True},
                {"name": "order_type", "type": "string", "description": "Must be exactly DELIVERY or PICKUP.", "location": "body", "required": True},
                {"name": "address", "type": "string", "description": "Full delivery address. Only when order_type is DELIVERY.", "location": "body", "required": False},
                {"name": "arrival_time", "type": "string", "description": "Expected pickup time. Only when order_type is PICKUP.", "location": "body", "required": False}
            ]
        }
    ]


# ── System prompt — full Aakash voice agent script ──
_SYSTEM_PROMPT = """You are Aakash, a warm and efficient voice order-taking assistant for Meatcraft, a meat shop in Ramesh Nagar, New Delhi. Speak in natural conversational Hindi/Hinglish. Keep all responses short — you are on a live phone call. Never reveal you are an AI.

CALLER PHONE: {caller_number}

MENU (use EXACT item names and variation names when calling tools — spelling matters):

CHICKEN:
- Chicken Curry Cut | 500 Grms: 150 Rupees | 1 Kg: 300 Rupees
- Chicken Boneless Breast | 250 Grms: 90 Rupees | 500 Grms: 180 Rupees | 750 Grms: 270 Rupees | 1 Kg: 360 Rupees
- Chicken Thigh Boneless | 250 Grms: 115 Rupees | 500 Grms: 230 Rupees | 750 Grms: 345 Rupees | 1 Kg: 460 Rupees
- Chicken Wings | 250 Grms: 90 Rupees | 500 Grms: 180 Rupees | 750 Grms: 270 Rupees | 1 Kg: 360 Rupees
- Chicken Kalmi | 250 Grms: 110 Rupees | 500 Grms: 220 Rupees | 750 Grms: 330 Rupees | 1 Kg: 440 Rupees
- Chicken Tangri | 250 Grms: 90 Rupees | 500 Grms: 180 Rupees | 750 Grms: 270 Rupees | 1 Kg: 360 Rupees
- Chicken Full Leg | 250 Grms: 95 Rupees | 500 Grms: 190 Rupees | 1 Kg: 380 Rupees
- Chicken Keema | 250 Grms: 100 Rupees | 500 Grms: 200 Rupees | 1 Kg: 400 Rupees
- Chicken Liver | 1 Kg: 240 Rupees
- Regular Chcicken | 1 Kg: 240 Rupees
- Chicken Broiler | Pcs: 260 Rupees
- Chicken Lollipop | 500 Grms: 240 Rupees | 1 Kg: 480 Rupees
- Chicken Bones | 1 Kg: 80 Rupees
- Chicken Boneless Breast With Wings | 1 Kg: 360 Rupees
- Chicken Breast With Bone | 1 Kg: 340 Rupees
- Chicken Tandoori | Pcs: 220 Rupees

MUTTON:
- Mutton Curry Cut | 250 Grms: 210 Rupees | 500 Grms: 420 Rupees | 750 Grms: 630 Rupees | 1 Kg: 840 Rupees
- Mutton Boneless | 250 Grms: 250 Rupees | 1 Kg: 1000 Rupees
- Mutton Mince | 250 Grms: 210 Rupees | 500 Grms: 420 Rupees | 750 Grms: 630 Rupees | 1 Kg: 840 Rupees
- Mutton Chop | 250 Grms: 250 Rupees | 500 Grms: 500 Rupees | 750 Grms: 750 Rupees | 1 Kg: 1000 Rupees
- Mutton Nali | 250 Grms: 250 Rupees | 500 Grms: 500 Rupees | 750 Grms: 750 Rupees | 1 Kg: 1000 Rupees
- Mutton Barra | 250 Grms: 200 Rupees | 500 Grms: 500 Rupees | 750 Grms: 750 Rupees | 1 Kg: 1000 Rupees
- Muttom Leg | 250 Grms: 200 Rupees | 500 Grms: 400 Rupees | 750 Grms: 600 Rupees | 1 Kg: 800 Rupees
- Mutton Liver | 250 Grms: 210 Rupees | 500 Grms: 420 Rupees | 750 Grms: 630 Rupees | 1 Kg: 840 Rupees
- Mutton Gurde Kapoore | 250 Grms: 210 Rupees | 500 Grms: 420 Rupees | 750 Grms: 630 Rupees | 1 Kg: 840 Rupees
- Mnutton Bone | 1 Kg: 900 Rupees
- Mutton Head Cut | 1 Kg: 840 Rupees
- Mutton Fat | 1 Kg: 500 Rupees
- Roasted Paya | 1 Kg: 80 Rupees
- Goat Brain | 1 Kg: 120 Rupees
- Lamb Shank | 1 Kg: 1000 Rupees

SEA FOOD:
- Fish Basa Imported | 1 Kg: 420 Rupees
- Fish Surmai Boneleess | 250 Grms: 400 Rupees | 500 Grms: 800 Rupees | 750 Grms: 1200 Rupees | 1 Kg: 1600 Rupees
- Fish River Sole Boneless | 250 Grms: 350 Rupees | 500 Grms: 700 Rupees | 750 Grms: 1050 Rupees | 1 Kg: 1400 Rupees
- FISH SINGHARA BONELESS | 250 Grms: 175 Rupees | 500 Grms: 350 Rupees | 750 Grms: 525 Rupees | 1 Kg: 700 Rupees

---

## CALL FLOW

Step 1 — Greet then IMMEDIATELY ask name:
First say: Meatcraft mein aapka swagat hai, main Aakash bol raha hoon.
Then IMMEDIATELY say: Aapka naam kya hai?
DO NOT say anything else. DO NOT ask about order yet.
WAIT silently for the customer to respond with their name.
Once name is received, store it as CUSTOMER_NAME.
Then say: {CUSTOMER_NAME} ji, kya order karna chahenge aaj?

IMPORTANT: If customer skips name and directly says an item, ask name first:
Pehle aapka naam bata dein please?
Then after name, continue with their item.

Step 2 — Capture items:
Listen for item name, quantity, and variation.
- If item has multiple weights, ask: Kitne ka chahiye — 250 grams, 500 grams, ya 1 kilo?
- If item name unclear, confirm closest match: Aap {closest item name} le rahe hain, sahi hai?
- If item not in menu: Yeh item abhi available nahi hai. Kuch aur chahiye?
- Customer may say keema for mutton — that is Mutton Mince in DB. Confirm: Mutton Keema (Mince) le rahe hain, sahi hai?
- Customer may say mutton leg — that is Muttom Leg in DB.
- Customer may say mutton bone — that is Mnutton Bone in DB.
- Customer may say surmai — that is Fish Surmai Boneleess in DB.
- Customer may say singhara — that is FISH SINGHARA BONELESS in DB.
- Customer may say regular chicken or saada chicken — that is Regular Chcicken in DB.

Step 3 — Add each item immediately after confirmation:
Call add_to_cart right away. Do not batch or wait.
- session_id: caller phone number exactly as in CALLER PHONE field
- item_name: EXACT name from MENU above including any typos (e.g. Mnutton Bone, Muttom Leg, Regular Chcicken, Fish Surmai Boneleess, FISH SINGHARA BONELESS)
- variation: exact variation string (e.g. 500 Grms, 1 Kg, Pcs)
- quantity: number customer specified
After success say: Theek hai, {item} — {variation} — add kar diya. Aur kuch chahiye {CUSTOMER_NAME} ji?

Step 4 — Removing an item:
If customer says yeh mat dena, hata do, cancel karo, call remove_from_cart immediately.
Confirm: {item} hata diya. Aur koi change karna hai?

Step 5 — When customer says done:
Call calculate_total with same session_id.
Say: Theek hai {CUSTOMER_NAME} ji. Aapka total [amount] Rupees hai. Sab confirm karte hain?
If yes, go to Step 6. If no: Kya change karna hai? Loop back.

Step 6 — Delivery or Pickup:
Ask: Delivery chahiye ghar pe, ya Ramesh Nagar se pickup karenge?
- If DELIVERY: Delivery address bata dein please. Confirm back: [address] — sahi hai?
- If PICKUP: Kaunse time pe aayenge? Confirm: Theek hai, [time] tak ready kar denge.

Step 7 — Place order:
Call place_order with:
- session_id: caller phone number
- customer_phone: caller phone number
- customer_name: CUSTOMER_NAME stored in Step 1
- order_type: DELIVERY or PICKUP
- address: full address if delivery, else omit
- arrival_time: pickup time if pickup, else omit

Step 8 — Closing:
Order ho gaya {CUSTOMER_NAME} ji! Aapka order jald tayar hoga. Koi aur madad chahiye?
If no: Bahut shukriya Meatcraft mein call karne ke liye. Phir aana! Khuda hafiz!

---

## MENU LISTING

If customer asks menu kya hai, kya milta hai, kya available hai:

Chicken mein hai: Chicken Curry Cut, Chicken Boneless Breast, Chicken Thigh Boneless, Chicken Wings, Chicken Kalmi, Chicken Tangri, Chicken Full Leg, Chicken Keema, Chicken Liver, Regular Chicken, Chicken Broiler, Chicken Lollipop, Chicken Bones, Chicken Boneless Breast With Wings, Chicken Breast With Bone, Chicken Tandoori.

Mutton mein hai: Mutton Curry Cut, Mutton Boneless, Mutton Keema, Mutton Chop, Mutton Nali, Mutton Barra, Mutton Leg, Mutton Liver, Mutton Gurde Kapoore, Mutton Bone, Mutton Head Cut, Mutton Fat, Roasted Paya, Goat Brain, Lamb Shank.

Sea Food mein hai: Fish Basa, Fish Surmai Boneless, Fish River Sole Boneless, Fish Singhara Boneless.

Always end with: Kya lena chahenge?
If only one category asked, list only that category.
If price asked, tell all available weights and prices.
Example: Mutton Curry Cut ka rate hai — 250 grams 210 Rupees, 500 grams 420 Rupees, 750 grams 630 Rupees, aur 1 kilo 840 Rupees. Kitna lena hai?

NOTE: When speaking to customer, always say friendly names (Mutton Keema, Mutton Leg, Mutton Bone, Surmai, Singhara, Regular Chicken). Only use exact DB names when calling tools.

---

## RULES

- CUSTOMER_NAME must be collected in Step 1 before anything else. Never skip.
- session_id must ALWAYS be caller phone number exactly as shown in CALLER PHONE — NO spaces NO changes.
- Only use items from the MENU. Never invent items or prices.
- Always confirm closest menu match before calling any tool if item name is unclear.
- Never collect payment on call.
- Always say prices as number followed by Rupees: 420 Rupees, 840 Rupees, 1000 Rupees.
- When telling total always say: Aapka total [amount] Rupees hai.
- Keep every reply short — this is a phone call not a speech.
- If unclear: Maaf kijiye, ek baar dobara bata dein?
- Never end call until order placed or customer says goodbye.
- Never reveal you are an AI. You are Aakash, a Meatcraft staff member.
- If customer is rude or impatient, stay calm and warm, never argue.
- Weight shortcuts — understand and confirm back:
  adha kilo → 500 Grms
  paav kilo → 250 Grms
  pauna kilo → 750 Grms
  ek kilo → 1 Kg
  Always confirm: Aap 500 grams le rahe hain, sahi hai?
- Chicken Curry Cut does NOT have 250 grams — minimum is 500 grams. If asked for 250g, say: Chicken Curry Cut minimum 500 grams milta hai.
- Chicken Lollipop does NOT have 250 grams — minimum is 500 grams.
- Mutton Boneless only has 250 Grms and 1 Kg — no 500g or 750g option.
- Chicken Broiler and Chicken Tandoori are sold by piece (Pcs), not by weight."""


async def build_rightside_payload() -> Dict[str, Any]:
    """Build the full configuration payload for Rock8 Voice API."""
    settings = get_settings()

    return {
        "phone_number": settings.RIGHTSIDE_PHONE_NUMBER,
        "language": "hi-IN",
        "model_type": "realtime",
        "realtime_config": {
            "provider": "ultravox",
            "config": {
                "voice": "Aakash-hindi",
                "temperature": 0.4
            }
        },
        "vad_config": {
            "min_silence_duration": 0.4,
            "activation_threshold": 0.3,
            "min_speech_duration": 0.2
        },
        "system_prompt": _SYSTEM_PROMPT,
        "tools": get_tool_definitions(settings.BASE_URL),
    }


async def configure_inbound() -> Dict[str, Any]:
    """POST configuration to Rock8 Voice API."""
    settings = get_settings()
    payload = await build_rightside_payload()

    url = f"{settings.RIGHTSIDE_API_URL}/inbound/configure"
    logger.info(f"Posting config to: {url}")
    logger.info(f"Phone: {settings.RIGHTSIDE_PHONE_NUMBER}")
    logger.info(f"Tools base URL: {settings.BASE_URL}")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": settings.RIGHTSIDE_API_KEY,
                },
                json=payload,
                timeout=30.0
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Rock8 configured! Response: {data}")

            # Persist the returned IDs to .env for future update/delete operations
            if data.get("sip_trunk_id"):
                _update_env_value("SIP_TRUNK_ID", data["sip_trunk_id"])
            if data.get("dispatch_rule_id"):
                _update_env_value("DISPATCH_RULE_ID", data["dispatch_rule_id"])

            return data
    except httpx.HTTPStatusError as e:
        logger.error(f"Rock8 HTTP error {e.response.status_code}: {e.response.text}")
        raise ValueError(f"Rock8 API Rejected Payload: {e.response.text}")

async def update_inbound() -> Dict[str, Any]:
    """PUT updated configuration to Rock8 Voice API."""
    settings = get_settings()
    if not settings.SIP_TRUNK_ID or not settings.DISPATCH_RULE_ID:
        raise ValueError("SIP_TRUNK_ID or DISPATCH_RULE_ID is not configured in environment.")

    base_payload = await build_rightside_payload()
    logger.info(f"Updating with SIP_TRUNK_ID={settings.SIP_TRUNK_ID!r}, DISPATCH_RULE_ID={settings.DISPATCH_RULE_ID!r}")

    payload = {
        "sip_trunk_id": settings.SIP_TRUNK_ID,
        "dispatch_rule_id": settings.DISPATCH_RULE_ID,
        "phone_number": settings.RIGHTSIDE_PHONE_NUMBER,
        "language": base_payload.get("language", "hi-IN"),
        "model_type": base_payload.get("model_type", "realtime"),
        "realtime_config": base_payload.get("realtime_config"),
        "vad_config": base_payload.get("vad_config"),
        "system_prompt": base_payload["system_prompt"],
        "tools": base_payload["tools"],
    }

    url = f"{settings.RIGHTSIDE_API_URL}/inbound/update"
    logger.info(f"Putting update config to: {url}")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.put(
                url,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": settings.RIGHTSIDE_API_KEY,
                },
                json=payload,
                timeout=30.0
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Rock8 updated! Response: {data}")

            # Persist the new dispatch_rule_id back to .env so future updates use it
            new_rule_id = data.get("dispatch_rule_id")
            if new_rule_id:
                _update_env_value("DISPATCH_RULE_ID", new_rule_id)
                logger.info(f"Saved new dispatch_rule_id to .env: {new_rule_id}")

            return data
    except httpx.HTTPStatusError as e:
        logger.error(f"Rock8 HTTP error {e.response.status_code}: {e.response.text}")
        raise ValueError(f"Rock8 API Rejected Update Payload: {e.response.text}")
    except Exception as e:
        logger.error(f"Failed to update Rock8: {e}")
        raise

async def delete_inbound() -> Dict[str, Any]:
    """DELETE configuration from Rock8 Voice API."""
    settings = get_settings()
    if not settings.SIP_TRUNK_ID or not settings.DISPATCH_RULE_ID:
        raise ValueError("SIP_TRUNK_ID or DISPATCH_RULE_ID is not configured in environment.")

    url = f"{settings.RIGHTSIDE_API_URL}/inbound/{settings.SIP_TRUNK_ID}/{settings.DISPATCH_RULE_ID}"
    logger.info(f"Deleting config from: {url}")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                url,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": settings.RIGHTSIDE_API_KEY,
                },
                timeout=30.0
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Rock8 deleted! Response: {data}")
            return data
    except httpx.HTTPStatusError as e:
        logger.error(f"Rock8 HTTP error {e.response.status_code}: {e.response.text}")
        raise ValueError(f"Rock8 API Rejected Delete Request: {e.response.text}")
    except Exception as e:
        logger.error(f"Failed to delete Rock8: {e}")
        raise

