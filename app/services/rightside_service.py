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

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

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


def get_tool_definitions() -> List[Dict[str, Any]]:
    """
    Define tools in Rock8 format using the URL from environment settings.
    Each parameter MUST have: name, type, description, location, required
    location can be: "body", "query", or "header"
    """
    settings = get_settings()
    base = settings.BASE_URL.rstrip('/')
    return [
        {
            "name": "search_menu",
            "description": (
                "Search the menu for items or categories. Call this whenever the customer asks "
                "what is available, asks for a specific category, or before adding an item if you "
                "are unsure of the exact name/sizes. "
                "Pass an empty query to get a list of categories. "
                "Pass a search term like 'chicken', 'mutton', 'liver', or 'masale' to get matching items."
            ),
            "method": "POST",
            "url": f"{base}/api/search_menu",
            "speak_during_execution": True,
            "speak_message": "ज़रा रुकिए, मैं menu check कर रही हूँ...",
            "messages": [{"type": "request-start", "content": "ज़रा रुकिए, मैं menu check कर रही हूँ..."}],
            "parameters": [
                {"name": "session_id", "type": "string", "description": "The exact assigned 6-digit session code.", "location": "body", "required": True},
                {"name": "caller_number", "type": "string", "description": "Caller's actual phone number.", "location": "body", "required": False},
                {"name": "query", "type": "string", "description": "Item name or category to search for (e.g. 'chicken', 'liver'). Can be omitted or empty to list all categories.", "location": "body", "required": False}
            ]
        },
        {
            "name": "add_to_cart",
            "description": (
                "Add a confirmed item to the shopping cart. "
                "CRITICAL RULES: "
                "(1) item_name MUST be an EXACT character-for-character match from the MENU. "
                "NEVER translate or substitute similar items (e.g., if customer says 'Mutton Keema' but menu has 'Mutton Mince', do NOT use 'Mutton Mince' — tell the customer it's not available and offer alternatives). "
                "(2) TWO MODES — choose ONE: "
                "  MODE A (standard): Pass variation (exact menu size like '500 Grms', '1 Kg') + quantity (integer). Use when customer asks for a standard pack size. "
                "  MODE B (custom weight): Pass custom_weight_kg (float, e.g. 4.2 or 0.75) ONLY. Do NOT pass variation or quantity. Use when the customer requests a non-standard weight like 4.2 kg or 750 grams. The backend computes the exact proportional price. "
                "(3) For MODE B, first call get_item_price (without budget) to get price_per_kg, compute price = custom_weight_kg * price_per_kg, confirm with customer, then call add_to_cart with custom_weight_kg. "
                "(4) ALL slots must be EXPLICITLY confirmed by the customer before calling this tool."
            ),
            "method": "POST",
            "url": f"{base}/api/add_to_cart",
            "speak_during_execution": True,
            "speak_message": "एक मिनट, मैं सिस्टम में update कर रही हूँ...",
            "messages": [{"type": "request-start", "content": "एक मिनट, मैं सिस्टम में update कर रही हूँ..."}],
            "parameters": [
                {"name": "session_id", "type": "string", "description": "The exact assigned 6-digit session code given to you.", "location": "body", "required": True},
                {"name": "caller_number", "type": "string", "description": "Caller's actual phone number from call metadata (e.g. +919876543210). Pass if available from metadata, otherwise omit.", "location": "body", "required": False},
                {"name": "item_name", "type": "string", "description": "The EXACT item name as it appears in the MENU — character for character, no translation, no paraphrasing.", "location": "body", "required": True},
                {"name": "variation", "type": "string", "description": "[MODE A only] Item variation e.g. '250 Grms', '500 Grms', '1 Kg', 'Pcs'. Omit in MODE B (custom_weight_kg) and for items with no variation.", "location": "body", "required": False},
                {"name": "quantity", "type": "integer", "description": "[MODE A only] Number of units of the specified variation. Default is 1. Omit in MODE B.", "location": "body", "required": False},
                {"name": "custom_weight_kg", "type": "number", "description": "[MODE B only] The exact weight in kilograms the customer wants (e.g. 4.2, 0.75, 3.214). The backend calculates the exact price proportionally. Do NOT use if customer asked for a standard menu variation size. Pass ONLY this field (not variation/quantity) for custom weights.", "location": "body", "required": False}
            ]
        },
        {
            "name": "remove_from_cart",
            "description": (
                "Remove an item from cart — fully or partially. "
                "If customer says 'hata do' or 'cancel' without specifying weight, omit quantity to remove the entire item. "
                "If customer says 'remove 1 kg' or '500 grams hata do', pass quantity (e.g. '1 Kg', '500 Grms') to remove only that weight."
            ),
            "method": "POST",
            "url": f"{base}/api/remove_from_cart",
            "speak_during_execution": True,
            "speak_message": "एक मिनट, मैं इसे हटा देती हूँ...",
            "messages": [{"type": "request-start", "content": "एक मिनट, मैं इसे हटा देती हूँ..."}],
            "parameters": [
                {"name": "session_id", "type": "string", "description": "The exact assigned 6-digit session code given to you.", "location": "body", "required": True},
                {"name": "item_name", "type": "string", "description": "Exact name of the menu item to remove.", "location": "body", "required": True},
                {"name": "quantity", "type": "string", "description": "Weight to remove, e.g. '1 Kg', '500 Grms'. OMIT this to remove the entire item. Pass it only when the customer wants partial removal.", "location": "body", "required": False}
            ]
        },
        {
            "name": "calculate_total",
            "description": "Get all items in cart and total price. Call after customer says done ordering.",
            "method": "POST",
            "url": f"{base}/api/calculate_total",
            "speak_during_execution": True,
            "speak_message": "ज़रा रुकिए, मैं आपका total check कर रही हूँ...",
            "messages": [{"type": "request-start", "content": "ज़रा रुकिए, मैं आपका total check कर रही हूँ..."}],
            "parameters": [
                {"name": "session_id", "type": "string", "description": "The exact assigned 6-digit session code given to you.", "location": "body", "required": True},
                {"name": "caller_number", "type": "string", "description": "Caller's actual phone number. Pass if available.", "location": "body", "required": False}
            ]
        },
        {
            "name": "get_cart",
            "description": (
                "Check current cart contents from the database. Call this when: "
                "(1) the customer asks what is in their cart, "
                "(2) you need to verify if an item was successfully added, "
                "(3) you need to check for duplicate items before adding. "
                "Returns the real cart state — do NOT rely on conversation memory for cart state."
            ),
            "method": "POST",
            "url": f"{base}/api/calculate_total",
            "speak_during_execution": True,
            "speak_message": "एक मिनट, मैं आपका cart check करती हूँ...",
            "messages": [{"type": "request-start", "content": "एक मिनट, मैं आपका cart check करती हूँ..."}],
            "parameters": [
                {"name": "session_id", "type": "string", "description": "The exact assigned 6-digit session code given to you.", "location": "body", "required": True},
                {"name": "caller_number", "type": "string", "description": "Caller phone if available.", "location": "body", "required": False}
            ]
        },
        {
            "name": "place_order",
            "description": "Place final confirmed order. Call EXACTLY ONCE — never retry. If it returns success=false, tell the customer and do NOT call again. Call ONLY after all items verified via calculate_total, delivery method confirmed, and customer name collected. IF NAME IS UNKNOWN, YOU MUST FIRST ASK THE CUSTOMER THEIR NAME AND WAIT FOR THEIR REPLY.",
            "method": "POST",
            "url": f"{base}/api/place_order",
            "speak_during_execution": True,
            "speak_message": "बस एक पल, मैं आपका order systems में डाल रही हूँ...",
            "messages": [{"type": "request-start", "content": "बस एक पल, मैं आपका order systems में डाल रही हूँ..."}],
            "parameters": [
                {"name": "session_id", "type": "string", "description": "The exact assigned 6-digit session code given to you.", "location": "body", "required": True},
                {"name": "caller_number", "type": "string", "description": "Caller's actual phone number from metadata. Pass if available, otherwise omit.", "location": "body", "required": False},
                {"name": "customer_phone", "type": "string", "description": "Same as caller_number. Optional.", "location": "body", "required": False},
                {"name": "customer_name", "type": "string", "description": "Customer's REAL name. Do NOT use fake names like 'Unknown', 'Customer', 'User', 'Guest'. IF YOU DO NOT KNOW THE NAME, YOU MUST ASK THE CUSTOMER BEFORE CALLING THIS TOOL. MUST be in English Latin script (e.g., 'Nikshit'). NEVER use Devanagari.", "location": "body", "required": True},
                {"name": "order_type", "type": "string", "description": "Must be exactly DELIVERY or PICKUP.", "location": "body", "required": True},
                {"name": "address", "type": "string", "description": "Full delivery address. Only when order_type is DELIVERY.", "location": "body", "required": False},
                {"name": "arrival_time", "type": "string", "description": "Expected pickup time. Only when order_type is PICKUP.", "location": "body", "required": False}
            ]
        },
        {
            "name": "get_item_price",
            "description": (
                "Look up pricing for a menu item and get the server-computed total price. THREE USE CASES: "
                "USE CASE 1 (custom weight, e.g. '3.3 kg mutton boneless'): "
                "  Call with item_name AND custom_weight_kg. Response gives computed_total_price (server-computed). "
                "  Confirm with customer: '[weight] kg [item] — [computed_total_price] Rupees. Add kar doon?' "
                "  On confirmation, call add_to_cart with custom_weight_kg_to_add (from the response). "
                "  NEVER compute the price yourself. ALWAYS use computed_total_price from the response. "
                "USE CASE 2 (budget-based, e.g. '300 rupees ka chicken'): "
                "  Call with item_name AND budget (rupees, as a number). "
                "  Response gives max_weight_human and actual_cost. "
                "  On confirmation, call add_to_cart with custom_weight_kg=custom_weight_kg_to_add. "
                "USE CASE 3 (price inquiry, e.g. 'mutton boneless ka rate kya hai'): "
                "  Call with item_name only. Response gives price_per_kg and variation details. "
                "CRITICAL: For ANY non-standard weight (3.3 kg, 2.5 kg, 750 grams, etc.), "
                "ALWAYS call this tool with custom_weight_kg FIRST, use the computed_total_price, "
                "and NEVER try to calculate the price yourself."
            ),
            "method": "POST",
            "url": f"{base}/api/get_item_price",
            "speak_during_execution": True,
            "speak_message": "एक मिनट, मैं price check कर रही हूँ...",
            "messages": [{"type": "request-start", "content": "एक मिनट, मैं price check कर रही हूँ..."}],
            "parameters": [
                {"name": "session_id", "type": "string", "description": "The exact assigned 6-digit session code given to you.", "location": "body", "required": True},
                {"name": "item_name", "type": "string", "description": "Exact menu item name to look up.", "location": "body", "required": True},
                {"name": "custom_weight_kg", "type": "number", "description": "Customer's requested weight in kilograms (e.g. 3.3, 0.75, 2.5). Pass this for ANY non-standard weight request. Server computes the total price — you MUST use the returned computed_total_price and NEVER calculate it yourself.", "location": "body", "required": False},
                {"name": "budget", "type": "number", "description": "Customer's budget in rupees. Pass ONLY for budget-based ordering (e.g. '300 rupees ka de do'). Omit for custom weight queries.", "location": "body", "required": False}
            ]
        }
    ]



async def build_rightside_payload(caller_number: str = "") -> Dict[str, Any]:
    """Build the full configuration payload for Rock8 Voice API.
    
    Args:
        caller_number: The caller's phone number, injected per-call by the webhook.
                       When empty (e.g. sync/preview), leaves the placeholder for reference.
    """
    settings = get_settings()
    now = datetime.datetime.now(IST)
    next_slot = (now + datetime.timedelta(minutes=30)).strftime("%H:%M")

    from app.database import db_instance

    # Read the prompt template from DB, fallback to file — SafeDict keeps un-replaced {placeholders} intact
    prompt_template = None
    try:
        if db_instance.db is not None:
            config_doc = await db_instance.db["config"].find_one({"type": "prompt"})
            if config_doc and "content" in config_doc:
                prompt_template = config_doc["content"]
                logger.info("Loaded prompt template from MongoDB")
    except Exception as e:
        logger.error(f"Failed to read prompt from DB: {e}")

    if not prompt_template:
        try:
            with open("prompt.txt", "r", encoding="utf-8") as f:
                prompt_template = f.read()
                logger.info("Loaded prompt from prompt.txt (fallback)")
        except Exception as e:
            logger.error(f"Failed to read prompt file: {e}")
            prompt_template = "You are रिया, a मीटक्राफ्ट assistant. Help the user order."

    import random
    session_id = str(random.randint(100000, 999999))
    
    format_kwargs = {
        "current_date": now.strftime("%Y-%m-%d"),
        # If caller_number provided by webhook, inject it; otherwise keep placeholder intact
        "caller_number": caller_number if caller_number else "{caller_number}",
        "session_id": session_id,
        "current_time": now.strftime("%H:%M"),
        "next_slot": next_slot,
    }
    system_prompt = prompt_template.format_map(SafeDict(**format_kwargs))

    return {
        "phone_number": settings.RIGHTSIDE_PHONE_NUMBER,
        "language": "hi",
        "voice": "faf0731e-dfb9-4cfc-8119-259a79b27e12",
        # "llm_config": {
        #     "provider": "gemini_live",
        #     "model": "gemini-3.1-pro-preview",
        #     "model_type": "standard"
        # },
        # "stt_config": {
        #     "provider": "deepgram",
        #     "config": {
        #         "model": "nova-3",
        #         "language": "hi"
        #     }
        # },
        "model_type": "realtime",
        "realtime_config": {
            "provider": "gemini_live",
            "config": {
                "model": "gemini-3.1-pro-preview"
            }
        },
        "vad_config": {
            "min_silence_duration": 0.25,
            "activation_threshold": 0.3,
            "min_speech_duration": 0.1
        },
        "system_prompt": system_prompt,
        "tools": get_tool_definitions()
    }



async def configure_inbound() -> Dict[str, Any]:
    """POST configuration to Rock8 Voice API."""
    settings = get_settings()
    
    # New API requires only phone_number and webhook_url
    # The full configuration (prompt, tools) is now fetched via the webhook
    payload = {
        "phone_number": settings.RIGHTSIDE_PHONE_NUMBER,
        "webhook_url": f"{settings.BASE_URL}/api/rightside/webhook"
    }

    url = f"{settings.RIGHTSIDE_API_URL}/inbound/configure"
    logger.info(f"Posting config to: {url}")
    logger.info(f"Phone: {settings.RIGHTSIDE_PHONE_NUMBER}")
    logger.info(f"Webhook URL: {payload['webhook_url']}")

    try:
        async with httpx.AsyncClient() as client:
            # Note: Content-Type and X-API-Key are required headers
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

    except httpx.HTTPStatusError as e:
        logger.error(f"Rock8 HTTP error {e.response.status_code}: {e.response.text}")
        raise ValueError(f"Rock8 API Rejected Payload: {e.response.text}")
    except Exception as e:
        logger.error(f"Failed to configure Rock8: {e}")
        raise

    return data

async def update_inbound() -> Dict[str, Any]:
    """PUT updated configuration to Rock8 Voice API."""
    settings = get_settings()
    if not settings.SIP_TRUNK_ID or not settings.DISPATCH_RULE_ID:
        raise ValueError("SIP_TRUNK_ID or DISPATCH_RULE_ID is not configured in environment.")

    logger.info(f"Updating with SIP_TRUNK_ID={settings.SIP_TRUNK_ID!r}, DISPATCH_RULE_ID={settings.DISPATCH_RULE_ID!r}")

    payload = {
        "sip_trunk_id": settings.SIP_TRUNK_ID,
        "dispatch_rule_id": settings.DISPATCH_RULE_ID,
        "phone_number": settings.RIGHTSIDE_PHONE_NUMBER,
        "webhook_url": f"{settings.BASE_URL}/api/rightside/webhook"
    }

    # API docs: PUT /inbound/update — both IDs go in the body, not the URL
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

    except httpx.HTTPStatusError as e:
        logger.error(f"Rock8 HTTP error {e.response.status_code}: {e.response.text}")
        raise ValueError(f"Rock8 API Rejected Update Payload: {e.response.text}")
    except Exception as e:
        logger.error(f"Failed to update Rock8: {e}")
        raise

    return data

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
    except httpx.HTTPStatusError as e:
        logger.error(f"Rock8 HTTP error {e.response.status_code}: {e.response.text}")
        raise ValueError(f"Rock8 API Rejected Delete Request: {e.response.text}")
    except Exception as e:
        logger.error(f"Failed to delete Rock8: {e}")
        raise

    return data

