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
            "name": "add_to_cart",
            "description": "Add an item to the shopping cart. Call IMMEDIATELY when customer confirms an item. One call per item.",
            "method": "POST",
            "url": f"{base}/api/add_to_cart",
            "headers": {},
            "parameters": [
                {"name": "session_id", "type": "string", "description": "Take the caller phone number exactly from the CALLER PHONE parameter.", "location": "body", "required": True},
                {"name": "item_name", "type": "string", "description": "Exact name of the menu item as listed in the menu including any typos e.g. Mnutton Bone, Muttom Leg, Regular Chcicken, Fish Surmai Boneleess, FISH SINGHARA BONELESS.", "location": "body", "required": True},
                {"name": "variation", "type": "string", "description": "Item variation e.g. 250 Grms, 500 Grms, 750 Grms, 1 Kg, Pcs. Omit only if item has no variation.", "location": "body", "required": False},
                {"name": "quantity", "type": "integer", "description": "Number of units. Default is 1.", "location": "body", "required": False}
            ]
        },
        {
            "name": "remove_from_cart",
            "description": "Remove a specific item from cart when customer asks to cancel or remove.",
            "method": "POST",
            "url": f"{base}/api/remove_from_cart",
            "headers": {},
            "parameters": [
                {"name": "session_id", "type": "string", "description": "Take the caller phone number exactly from the CALLER PHONE parameter. Must match value used in add_to_cart.", "location": "body", "required": True},
                {"name": "item_name", "type": "string", "description": "Exact name of the menu item to remove including any DB typos.", "location": "body", "required": True},
                {"name": "variation", "type": "string", "description": "Variation of item to remove if applicable.", "location": "body", "required": False}
            ]
        },
        {
            "name": "calculate_total",
            "description": "Get all items in cart and total price. Call after customer says done ordering.",
            "method": "POST",
            "url": f"{base}/api/calculate_total",
            "headers": {},
            "parameters": [
                {"name": "session_id", "type": "string", "description": "Take the caller phone number exactly from the CALLER PHONE parameter. Must match value used in add_to_cart.", "location": "body", "required": True}
            ]
        },
        {
            "name": "place_order",
            "description": "Place final confirmed order. Call ONLY after items, total, delivery method and name all confirmed.",
            "method": "POST",
            "url": f"{base}/api/place_order",
            "headers": {},
            "parameters": [
                {"name": "session_id", "type": "string", "description": "Take the caller phone number exactly from the CALLER PHONE parameter. Must match value used in add_to_cart.", "location": "body", "required": True},
                {"name": "customer_phone", "type": "string", "description": "Take the caller phone number exactly from the CALLER PHONE parameter.", "location": "body", "required": True},
                {"name": "customer_name", "type": "string", "description": "Customer name collected at start of call in Step 1.", "location": "body", "required": True},
                {"name": "order_type", "type": "string", "description": "Must be exactly DELIVERY or PICKUP.", "location": "body", "required": True},
                {"name": "address", "type": "string", "description": "Full delivery address. Only when order_type is DELIVERY.", "location": "body", "required": False},
                {"name": "arrival_time", "type": "string", "description": "Expected pickup time. Only when order_type is PICKUP.", "location": "body", "required": False}
            ]
        }
    ]


async def build_rightside_payload() -> Dict[str, Any]:
    """Build the full configuration payload for Rock8 Voice API."""
    settings = get_settings()
    now = datetime.datetime.now()
    next_slot = (now + datetime.timedelta(minutes=30)).strftime("%H:%M")
    menu_summary = await get_formatted_menu_summary()

    # Read the prompt template from file — SafeDict keeps un-replaced {placeholders} intact
    try:
        with open("my meatcraftprompt.txt", "r", encoding="utf-8") as f:
            prompt_template = f.read()
    except Exception as e:
        logger.error(f"Failed to read prompt file: {e}")
        prompt_template = "You are Aakash, a Meatcraft assistant. Help the user order."

    format_kwargs = {
        "current_date": now.strftime("%Y-%m-%d"),
        "caller_number": "{caller_number}",
        "menu_items": menu_summary,
        "current_time": now.strftime("%H:%M"),
        "next_slot": next_slot,
    }
    system_prompt = prompt_template.format_map(SafeDict(**format_kwargs))

    return {
        "phone_number": settings.RIGHTSIDE_PHONE_NUMBER,
        "language": "hi-IN",
        "model_type": "realtime",
        "realtime_config": {
            "provider": "ultravox",
            "config": {
                "voice": "Monika-English-Indian",
                "temperature": 0.4
            }
        },
        "vad_config": {
            "min_silence_duration": 0.4,
            "activation_threshold": 0.3,
            "min_speech_duration": 0.2
        },
        "system_prompt": system_prompt,
        "tools": get_tool_definitions(),
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
        # phone_number intentionally omitted — including it triggers a SIP trunk
        # update internally (per Rock8 docs), which fails with "trunk id must not be set"
        "language": base_payload.get("language", "hi-IN"),
        "model_type": base_payload.get("model_type", "realtime"),
        "realtime_config": base_payload.get("realtime_config"),
        "vad_config": base_payload.get("vad_config"),
        "system_prompt": base_payload["system_prompt"],
        "tools": base_payload["tools"],
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

