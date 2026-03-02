import logging
import httpx
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect
from app.config import get_settings
from app.services.menu_service import get_menu
import datetime

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Voice"])
settings = get_settings()

# No longer defined as a hardcoded constant, read from file instead.

def get_ultravox_tools(base_url: str):
    """Define tools for Ultravox agent."""
    return [
        {
            "temporary_tool": {
                "model_tool_definition": {
                    "name": "add_to_cart",
                    "description": "Add an item to the shopping cart. Ask for variation if available in menu.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string"},
                            "item_name": {"type": "string"},
                            "variation": {"type": "string"},
                            "quantity": {"type": "integer", "default": 1}
                        },
                        "required": ["session_id", "item_name"]
                    }
                },
                "http": {
                    "url": f"{base_url}/api/add_to_cart",
                    "method": "POST"
                }
            }
        },
        {
            "temporary_tool": {
                "model_tool_definition": {
                    "name": "calculate_total",
                    "description": "Get all items currently in the cart and the total amount.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string"}
                        },
                        "required": ["session_id"]
                    }
                },
                "http": {
                    "url": f"{base_url}/api/calculate_total",
                    "method": "POST"
                }
            }
        },
        {
            "temporary_tool": {
                "model_tool_definition": {
                    "name": "remove_from_cart",
                    "description": "Remove an item from the shopping cart.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string"},
                            "item_name": {"type": "string"},
                            "variation": {"type": "string"}
                        },
                        "required": ["session_id", "item_name"]
                    }
                },
                "http": {
                    "url": f"{base_url}/api/remove_from_cart",
                    "method": "POST"
                }
            }
        },
        {
            "temporary_tool": {
                "model_tool_definition": {
                    "name": "place_order",
                    "description": "Place the final order from the cart items.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string"},
                            "customer_phone": {"type": "string"},
                            "customer_name": {"type": "string"},
                            "order_type": {"type": "string", "enum": ["DELIVERY", "PICKUP"]},
                            "address": {"type": "string"},
                            "arrival_time": {"type": "string"}
                        },
                        "required": ["session_id", "customer_phone", "customer_name", "order_type"]
                    }
                },
                "http": {
                    "url": f"{base_url}/api/place_order",
                    "method": "POST"
                }
            }
        }
    ]

async def get_formatted_menu_summary():
    """Fetch menu and format it as a readable string for the system prompt."""
    try:
        menu_data = await get_menu()
        summary = []
        categories = menu_data.get("categories", [])
        items = menu_data.get("items", [])
        
        for cat in categories:
            cat_name = cat.get("categoryname")
            cat_id = cat.get("categoryid")
            cat_items = [i.get("itemname") for i in items if i.get("item_categoryid") == cat_id and i.get("in_stock") == "2"]
            if cat_items:
                summary.append(f"- {cat_name}: {', '.join(cat_items)}")
        
        return "\n".join(summary)
    except Exception as e:
        logger.error(f"Failed to format menu: {e}")
        return "Menu items currently unavailable."

@router.post("/voice/incoming")
async def handle_incoming_call(request: Request):
    """
    Twilio Webhook: Triggered when a customer calls the Twilio number.
    Initializes an Ultravox session with Kiran Hinglish persona and bridges the call.
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    from_phone = form_data.get("From")
    
    logger.info(f"Incoming call from {from_phone} (SID: {call_sid})")

    # 1. Prepare dynamic prompt values
    now = datetime.datetime.now()
    next_slot = (now + datetime.timedelta(minutes=30)).strftime("%H:%M")
    menu_summary = await get_formatted_menu_summary()
    
    try:
        with open("my meatcraftprompt.txt", "r", encoding="utf-8") as f:
            prompt_template = f.read()
    except Exception as e:
        logger.error(f"Failed to read prompt file: {e}")
        prompt_template = "You are Kiran, a restaurant assistant for Meatcraft. Help the user order."

    system_prompt = prompt_template.format(
        current_date=now.strftime("%Y-%m-%d"),
        caller_number=from_phone,
        menu_items=menu_summary,
        current_time=now.strftime("%H:%M"),
        next_slot=next_slot,
        cart_id=call_sid
    )

    # 2. Create Ultravox Session
    try:
        async with httpx.AsyncClient() as client:
            ultravox_resp = await client.post(
                "https://api.ultravox.ai/api/sessions",
                headers={
                    "X-API-Key": settings.ULTRAVOX_API_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "system_prompt": system_prompt,
                    "model": "fixie-ai/ultravox-70b-v0.5",
                    "voice": "kiran", # Assuming this ID exists or falls back
                    "first_speaker": "FIRST_SPEAKER_AGENT",
                    "selected_tools": get_ultravox_tools(settings.BASE_URL)
                }
            )
            ultravox_resp.raise_for_status()
            session_data = ultravox_resp.json()
            join_url = session_data.get("joinUrl")
            
            logger.info(f"Ultravox session created: {join_url}")

    except Exception as e:
        logger.error(f"Failed to create Ultravox session: {e}")
        # Return fallback TwiML
        twiml = VoiceResponse()
        twiml.say("Sorry, our AI assistant is unavailable. Please try again later.")
        return Response(content=str(twiml), media_type="text/xml")

    # 2. Return TwiML to bridge call to Ultravox
    twiml = VoiceResponse()
    connect = Connect()
    # Using the standard Ultravox-Twilio bridge integration
    # Note: Ultravox provides a specific WebSocket endpoint for Twilio
    connect.stream(url=join_url) 
    twiml.append(connect)

    return Response(content=str(twiml), media_type="text/xml")
