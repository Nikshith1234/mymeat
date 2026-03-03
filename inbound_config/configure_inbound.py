import requests
import json
import sys
import asyncio
from pathlib import Path

# Add project root to path so we can import backend packages
root_dir = str(Path(__file__).parent.parent)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from app.config import get_settings
from app.services.rightside_service import build_rightside_payload

settings = get_settings()

# API Endpoint
url = f"{settings.RIGHTSIDE_API_URL}/inbound/configure"

HEADERS = {
    "Content-Type": "application/json",
    "X-API-Key": settings.RIGHTSIDE_API_KEY,
}


def configure_inbound():
    print(f"Configuring inbound number: {settings.RIGHTSIDE_PHONE_NUMBER}")
    print(f"Using API URL: {url}")
    print(f"Using Base URL for tools: {settings.BASE_URL}")

    # Build the full payload dynamically (prompt + menu + tools)
    payload = asyncio.run(build_rightside_payload())

    try:
        response = requests.post(url, json=payload, headers=HEADERS)
        if not response.ok:
            print(f"Error {response.status_code}: {response.reason}")
            try:
                print("Server response:", json.dumps(response.json(), indent=2))
            except Exception:
                print("Raw response:", response.text)
        else:
            data = response.json()
            print("Agent Configured Successfully!")
            print(json.dumps(data, indent=2))

            # Save the IDs back for future use
            sip_trunk_id = data.get("sip_trunk_id", "")
            dispatch_rule_id = data.get("dispatch_rule_id", "")

            if sip_trunk_id and dispatch_rule_id:
                print("\n--- Save these to your .env ---")
                print(f"SIP_TRUNK_ID={sip_trunk_id}")
                print(f"DISPATCH_RULE_ID={dispatch_rule_id}")
                print("--------------------------------\n")

    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")


if __name__ == "__main__":
    configure_inbound()
