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
            "description": "Add an item to the shopping cart. Call this tool IMMEDIATELY every time the customer confirms they want a specific item — do not wait until the end. One call per item.",
            "method": "POST",
            "url": f"{base_url}/api/add_to_cart",
            "headers": {},
            "parameters": [
                {"name": "session_id", "type": "string", "description": "The phone number of the caller currently on this call. Use the caller's actual phone number as the session identifier.", "location": "body", "required": True},
                {"name": "item_name", "type": "string", "description": "Exact name of the menu item as listed in the menu (e.g. 'Chicken Momos', 'Lamb Shank')", "location": "body", "required": True},
                {"name": "variation", "type": "string", "description": "Item variation if applicable (e.g. '250gm', '500gm', '1kg', 'Half', 'Full'). Omit if no variation.", "location": "body", "required": False},
                {"name": "quantity", "type": "integer", "description": "Number of units to add. Default is 1.", "location": "body", "required": False}
            ]
        },
        {
            "name": "calculate_total",
            "description": "Get all items currently in the cart and the total price. Call this after all items have been added and the customer says they are done ordering, before asking for order confirmation.",
            "method": "POST",
            "url": f"{base_url}/api/calculate_total",
            "headers": {},
            "parameters": [
                {"name": "session_id", "type": "string", "description": "The phone number of the caller currently on this call. Must be the same value used in add_to_cart.", "location": "body", "required": True}
            ]
        },
        {
            "name": "remove_from_cart",
            "description": "Remove a specific item from the cart. Call this when the customer asks to remove or cancel a particular item.",
            "method": "POST",
            "url": f"{base_url}/api/remove_from_cart",
            "headers": {},
            "parameters": [
                {"name": "session_id", "type": "string", "description": "The phone number of the caller currently on this call. Must be the same value used in add_to_cart.", "location": "body", "required": True},
                {"name": "item_name", "type": "string", "description": "Exact name of the menu item to remove", "location": "body", "required": True},
                {"name": "variation", "type": "string", "description": "Variation of the item to remove, if applicable", "location": "body", "required": False}
            ]
        },
        {
            "name": "place_order",
            "description": "Place the final order. Call this ONLY after: (1) all items are in the cart, (2) the customer has confirmed the total, (3) the customer has confirmed delivery or pickup, and (4) you have the customer's name. This sends the payment link to the customer's WhatsApp.",
            "method": "POST",
            "url": f"{base_url}/api/place_order",
            "headers": {},
            "parameters": [
                {"name": "session_id", "type": "string", "description": "The phone number of the caller currently on this call. Must be the same value used in add_to_cart.", "location": "body", "required": True},
                {"name": "customer_phone", "type": "string", "description": "The caller's phone number (same as session_id)", "location": "body", "required": True},
                {"name": "customer_name", "type": "string", "description": "Customer's name as provided during the call. Ask for it if not given.", "location": "body", "required": True},
                {"name": "order_type", "type": "string", "description": "Must be exactly 'DELIVERY' or 'PICKUP'", "location": "body", "required": True},
                {"name": "address", "type": "string", "description": "Full delivery address. Required only when order_type is DELIVERY.", "location": "body", "required": False},
                {"name": "arrival_time", "type": "string", "description": "Expected pickup time. Required only when order_type is PICKUP.", "location": "body", "required": False}
            ]
        }
    ]


async def build_rightside_payload() -> Dict[str, Any]:
    """Build the full configuration payload for Rock8 Voice API."""
    settings = get_settings()
    now = datetime.datetime.now()
    next_slot = (now + datetime.timedelta(minutes=30)).strftime("%H:%M")
    menu_summary = await get_formatted_menu_summary()

    # Read the prompt template
    try:
        with open("my meatcraftprompt.txt", "r", encoding="utf-8") as f:
            prompt_template = f.read()
    except Exception as e:
        logger.error(f"Failed to read prompt file: {e}")
        prompt_template = "You are Kiran, a restaurant assistant for Meatcraft. Help the user order."

    # Use SafeDict to format so any brackets inside the prompt (like {list_items}) don't break it
    format_kwargs = {
        "current_date": now.strftime("%Y-%m-%d"),
        "caller_number": "{caller_number}",
        "menu_items": menu_summary,
        "current_time": now.strftime("%H:%M"),
        "next_slot": next_slot,
        "cart_id": "{session_id}"
    }
    system_prompt = prompt_template.format_map(SafeDict(**format_kwargs))

    return {
        "phone_number": settings.RIGHTSIDE_PHONE_NUMBER,
        "system_prompt": system_prompt,
        "tools": get_tool_definitions(settings.BASE_URL),
        "language": "hi-IN",
        "model_type": "standard",
        "AllowedNumbers": ["*"],
        # ── STT: Deepgram Nova-2 tuned for Hindi ──
        "stt_config": {
            "provider": "deepgram",
            "config": {
                "model": "nova-2",
                "language": "hi",
                "smart_format": True,
                "punctuate": True,
                "interim_results": True,
                "endpointing": 300,
            }
        },
        # ── LLM: gpt-4o-mini — fast, cheap, good enough for ordering ──
        "llm_config": {
            "provider": "openai",
            "config": {
                "model": "gpt-4o-mini"
            }
        },
        # ── TTS: Cartesia sonic-multilingual (handles Hindi well) ──
        "tts_config": {
            "provider": "cartesia",
            "config": {
                "model": "sonic-multilingual",
                "language": "hi"
            }
        },
        # ── VAD: Tighter settings so it cuts in faster ──
        "vad_config": {
            "min_silence_duration": 0.4,
            "activation_threshold": 0.3,
            "min_speech_duration": 0.2
        }
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
        "system_prompt": base_payload["system_prompt"],
        "tools": base_payload["tools"],
        "language": base_payload.get("language", "hi-IN"),
        "model_type": base_payload.get("model_type", "standard"),
        "stt_config": base_payload.get("stt_config"),
        "llm_config": base_payload.get("llm_config"),
        "tts_config": base_payload.get("tts_config"),
        "vad_config": base_payload.get("vad_config"),
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

