"""Check what phone numbers are stored in recent orders on Render."""
import httpx
import asyncio
import json

async def check():
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://mymeat-afum.onrender.com/api/orders")
        orders = r.json()
        print(f"Total orders: {len(orders)}\n")
        for o in orders:
            print(f"order_id:       {o['order_id']}")
            print(f"customer_phone: {o.get('customer_phone', 'N/A')}")
            print(f"customer_name:  {o.get('customer_name', 'N/A')}")
            print(f"timestamp:      {o.get('timestamp', 'N/A')}")
            print(f"pos_status:     {o.get('pos_status', 'N/A')}")
            print("-" * 40)

asyncio.run(check())
