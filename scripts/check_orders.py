import httpx
import asyncio
import json

async def check_orders():
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://mymeat-afum.onrender.com/api/orders")
        orders = r.json()
        print(f"Total orders: {len(orders)}")
        for o in orders:
            print(f"  {o['order_id']} | {o.get('timestamp','?')} | pos_status={o.get('pos_status','?')} | {o.get('customer_name','?')}")

asyncio.run(check_orders())
