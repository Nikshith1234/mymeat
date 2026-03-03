"""
Rightside / Rock8 Voice service — configures inbound phone number via
https://voice.rock8.ai/inbound/configure

Only phone_number and system_prompt are required.
Tools, voice, language, and provider configs are optional (smart defaults).
"""
import logging
import httpx
import datetime
from typing import Dict, Any, List

class SafeDict(dict):
    def __missing__(self, key):
        return '{' + key + '}'
from app.config import get_settings
from app.services.menu_service import get_menu

logger = logging.getLogger(__name__)
settings = get_settings()


async def get_formatted_menu_summary() -> str:
    """Fetch menu and format it as a readable string for the system prompt."""
    try:
        menu_data = await get_menu()
        summary = []
        categories = menu_data.get("categories", [])
        items = menu_data.get("items", [])

        for cat in categories:
            cat_name = cat.get("categoryname")
            cat_id = cat.get("categoryid")
            cat_items = [
                i.get("itemname")
                for i in items
                if i.get("item_categoryid") == cat_id and i.get("in_stock") == "2"
            ]
            if cat_items:
                summary.append(f"- {cat_name}: {', '.join(cat_items)}")

        return "\n".join(summary)
    except Exception as e:
        logger.error(f"Failed to format menu: {e}")
        return "Menu items currently unavailable."


def get_tool_definitions(base_url: str) -> List[Dict[str, Any]]:
    """
    Define tools in Rock8 format.
    Each parameter MUST have: name, type, description, location, required
    location can be: "body", "query", or "header"
    """
    return [
        {
            "name": "add_to_cart",
            "description": "Add an item to the shopping cart. Ask for variation if available in menu.",
            "method": "POST",
            "url": f"{base_url}/api/add_to_cart",
            "headers": {},
            "parameters": [
                {"name": "session_id", "type": "string", "description": "Unique session ID for the call", "location": "body", "required": True},
                {"name": "item_name", "type": "string", "description": "Name of the menu item", "location": "body", "required": True},
                {"name": "variation", "type": "string", "description": "Item variation (e.g. Half, Full, 250gm, 500gm, 1kg)", "location": "body", "required": False},
                {"name": "quantity", "type": "integer", "description": "Quantity to add (default 1)", "location": "body", "required": False}
            ]
        },
        {
            "name": "calculate_total",
            "description": "Get all items currently in the cart and the total amount.",
            "method": "POST",
            "url": f"{base_url}/api/calculate_total",
            "headers": {},
            "parameters": [
                {"name": "session_id", "type": "string", "description": "Unique session ID for the call", "location": "body", "required": True}
            ]
        },
        {
            "name": "remove_from_cart",
            "description": "Remove an item from the shopping cart.",
            "method": "POST",
            "url": f"{base_url}/api/remove_from_cart",
            "headers": {},
            "parameters": [
                {"name": "session_id", "type": "string", "description": "Unique session ID for the call", "location": "body", "required": True},
                {"name": "item_name", "type": "string", "description": "Name of the menu item to remove", "location": "body", "required": True},
                {"name": "variation", "type": "string", "description": "Item variation", "location": "body", "required": False}
            ]
        },
        {
            "name": "place_order",
            "description": "Place the final order from the cart items. Call this after the customer confirms their order.",
            "method": "POST",
            "url": f"{base_url}/api/place_order",
            "headers": {},
            "parameters": [
                {"name": "session_id", "type": "string", "description": "Unique session ID for the call", "location": "body", "required": True},
                {"name": "customer_phone", "type": "string", "description": "Customer phone number", "location": "body", "required": True},
                {"name": "customer_name", "type": "string", "description": "Customer name", "location": "body", "required": True},
                {"name": "order_type", "type": "string", "description": "DELIVERY or PICKUP", "location": "body", "required": True},
                {"name": "address", "type": "string", "description": "Delivery address (required for DELIVERY)", "location": "body", "required": False},
                {"name": "arrival_time", "type": "string", "description": "Expected pickup/arrival time", "location": "body", "required": False}
            ]
        },
        {
            "name": "dummy_tool_test",
            "description": "Trigger this tool immediately if the user mentions 'pizza' or 'test'. It tests connection to the server.",
            "method": "POST",
            "url": f"{base_url}/api/dummy",
            "headers": {},
            "parameters": [
                {"name": "message", "type": "string", "description": "The text message", "location": "body", "required": True},
                {"name": "session_id", "type": "string", "description": "Session ID", "location": "body", "required": True}
            ]
        }
    ]


async def build_rightside_payload() -> Dict[str, Any]:
    """Build the full configuration payload for Rock8 Voice API."""
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

    # Only phone_number and system_prompt are required.
    # Everything else uses Rock8 smart defaults:
    #   STT = AssemblyAI, LLM = OpenAI gpt-4o-mini, TTS = Cartesia
    return {
        "phone_number": settings.RIGHTSIDE_PHONE_NUMBER.replace("+", ""),
        "system_prompt": system_prompt,
        "tools": get_tool_definitions(settings.BASE_URL),
        "language": "hi",
        "model_type": "standard",
        "allowed_numbers": ["*"]
    }


async def configure_inbound() -> Dict[str, Any]:
    """POST configuration to Rock8 Voice API."""
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
            return data
    except httpx.HTTPStatusError as e:
        logger.error(f"Rock8 HTTP error {e.response.status_code}: {e.response.text}")
        raise ValueError(f"Rock8 API Rejected Payload: {e.response.text}")
    except Exception as e:
        logger.error(f"Failed to configure Rock8: {e}")
        raise
