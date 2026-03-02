"""
Rightside AI service — configures inbound phone number with prompt + tools.
No API key required. Just POST the configuration payload.
"""
import logging
import httpx
import datetime
from typing import Dict, Any, List
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
    """Define tools in Rightside format."""
    return [
        {
            "name": "add_to_cart",
            "description": "Add an item to the shopping cart. Ask for variation if available in menu.",
            "method": "POST",
            "url": f"{base_url}/api/add_to_cart",
            "headers": {},
            "parameters": [
                {"name": "session_id", "type": "string", "description": "Unique session ID", "required": True},
                {"name": "item_name", "type": "string", "description": "Name of the menu item", "required": True},
                {"name": "variation", "type": "string", "description": "Item variation (e.g. Half, Full)", "required": False},
                {"name": "quantity", "type": "integer", "description": "Quantity to add", "required": False}
            ]
        },
        {
            "name": "calculate_total",
            "description": "Get all items currently in the cart and the total amount.",
            "method": "POST",
            "url": f"{base_url}/api/calculate_total",
            "headers": {},
            "parameters": [
                {"name": "session_id", "type": "string", "description": "Unique session ID", "required": True}
            ]
        },
        {
            "name": "remove_from_cart",
            "description": "Remove an item from the shopping cart.",
            "method": "POST",
            "url": f"{base_url}/api/remove_from_cart",
            "headers": {},
            "parameters": [
                {"name": "session_id", "type": "string", "description": "Unique session ID", "required": True},
                {"name": "item_name", "type": "string", "description": "Name of the menu item", "required": True},
                {"name": "variation", "type": "string", "description": "Item variation", "required": False}
            ]
        },
        {
            "name": "place_order",
            "description": "Place the final order from the cart items.",
            "method": "POST",
            "url": f"{base_url}/api/place_order",
            "headers": {},
            "parameters": [
                {"name": "session_id", "type": "string", "description": "Unique session ID", "required": True},
                {"name": "customer_phone", "type": "string", "description": "Phone number", "required": True},
                {"name": "customer_name", "type": "string", "description": "Customer name", "required": True},
                {"name": "order_type", "type": "string", "description": "DELIVERY or PICKUP", "required": True},
                {"name": "address", "type": "string", "description": "Delivery address", "required": False},
                {"name": "arrival_time", "type": "string", "description": "Expected arrival time", "required": False}
            ]
        }
    ]


async def build_rightside_payload() -> Dict[str, Any]:
    """Build the full Rightside configuration payload."""
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

    system_prompt = prompt_template.format(
        current_date=now.strftime("%Y-%m-%d"),
        caller_number="{caller_number}",  # Rightside will inject this at call time
        menu_items=menu_summary,
        current_time=now.strftime("%H:%M"),
        next_slot=next_slot,
        cart_id="{session_id}"  # Rightside will inject this at call time
    )

    return {
        "phone_number": settings.RIGHTSIDE_PHONE_NUMBER,
        "system_prompt": system_prompt,
        "tools": get_tool_definitions(settings.BASE_URL),
        "voice": "kiran",
        "language": "hi-IN",
        "model_type": "standard",
        "stt_config": {
            "provider": "google",
            "config": {"language_code": "hi-IN"}
        },
        "llm_config": {
            "provider": "openai",
            "config": {}
        },
        "tts_config": {
            "provider": "elevenlabs",
            "config": {}
        },
        "realtime_config": {
            "provider": "livekit",
            "config": {}
        },
        "vad_config": {
            "min_silence_duration": 0.1,
            "activation_threshold": 0.4,
            "min_speech_duration": 0.4
        }
    }


async def configure_inbound() -> Dict[str, Any]:
    """POST configuration to Rightside AI. No API key needed."""
    payload = await build_rightside_payload()

    logger.info(f"Sending config to Rightside for phone: {settings.RIGHTSIDE_PHONE_NUMBER}")
    logger.info(f"Tools pointing to BASE_URL: {settings.BASE_URL}")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.RIGHTSIDE_API_URL}/inbound/configure",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=30.0
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Rightside configured successfully: {data}")
            return data
    except httpx.HTTPStatusError as e:
        logger.error(f"Rightside HTTP error {e.response.status_code}: {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"Failed to configure Rightside: {e}")
        raise
