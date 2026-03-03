import requests
import json
import sys
from pathlib import Path

# Add project root to path so we can import backend packages
root_dir = str(Path(__file__).parent.parent)
if root_dir not in sys.path:
    sys.path.append(root_dir)

import asyncio
from app.config import get_settings
from app.services.rightside_service import build_rightside_payload

settings = get_settings()

# API Endpoint
url = "https://voice.rock8.ai/inbound/update"

HEADERS = {
    "Content-Type": "application/json",
    "X-API-Key": settings.RIGHTSIDE_API_KEY,
}

SIP_TRUNK_ID = settings.SIP_TRUNK_ID
DISPATCH_RULE_ID = settings.DISPATCH_RULE_ID
def update_inbound():
    # Build payload dynamically from rightside_service 
    # This automatically includes prompt, menu.txt summary, and the tools
    base_payload = asyncio.run(build_rightside_payload())
    
    payload = {
        "sip_trunk_id": SIP_TRUNK_ID,
        "dispatch_rule_id": DISPATCH_RULE_ID,
        "system_prompt": base_payload["system_prompt"],
        "tools": base_payload["tools"],
        "voice": "female",
        "language": "hi-IN",
        "model_type": "standard",
        "stt_config": {
            "provider": "deepgram",
            "config": {
                "model": "nova-2",
                "language": "hi"
            }
        },
        "llm_config": {
            "provider": "openai",
            "config": {
                "model": "gpt-4o"
            }
        },
        "tts_config": {
            "provider": "cartesia",
            "config": {
                "model": "sonic-english",
                "voice_id": "your-voice-id"  # NOTE: Replace 'your-voice-id' with Cartesia ID if it rings without picking up
            }
        },
        "vad_config": {
            "min_silence_duration": 0.6,
            "activation_threshold": 0.4,
            "min_speech_duration": 0.3
        }
    }

    print(f"Updating configuration for SIP Trunk: {SIP_TRUNK_ID}")
    try:
        response = requests.put(url, json=payload, headers=HEADERS)
        if not response.ok:
            print(f"Error {response.status_code}: {response.reason}")
            try:
                print("Server response:", json.dumps(response.json(), indent=2))
            except Exception:
                print("Raw response:", response.text)
        else:
            print("Agent Updated Successfully!")
            print(json.dumps(response.json(), indent=2))
            
            # NOTE: Be sure to update your saved dispatch_rule_id with the one returned here
            # I will automatically save the new dispatch ID back into the script for you via a separate process if needed.
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    update_inbound()
