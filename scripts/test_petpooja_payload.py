"""
Quick test: build and print the PetPooja payload for a sample order.
Run from the project root: python scripts/test_petpooja_payload.py
"""
import sys, os, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.petpooja_service import build_petpooja_payload

# ── Mock order object ──────────────────────────────────────────────────────
class MockOrder:
    order_id      = "MC-9925GD"
    customer_name = "Aakash"
    customer_phone= "+919876543210"
    address       = None
    order_type    = "PICKUP"
    total_amount  = 720.0

# ── Mock order items ───────────────────────────────────────────────────────
class MockItem:
    def __init__(self, name, variation, qty, price, final_price):
        self.item_name   = name
        self.variation   = variation
        self.quantity    = qty
        self.price       = price
        self.final_price = final_price

mock_items = [
    MockItem("Chicken Curry Cut", "1 Kg",    1, 300.0, 300.0),
    MockItem("Mutton Curry Cut",  "500 Grms",1, 420.0, 420.0),
]

# ── Build & print ──────────────────────────────────────────────────────────
payload = build_petpooja_payload(MockOrder(), mock_items)
print(json.dumps(payload, indent=2))
