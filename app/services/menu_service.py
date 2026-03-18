"""
Menu service — fetches and caches menu from local file.
Validates items and variations before adding to cart.
"""
import time
import logging
from typing import Optional, Dict, Any, List

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
# NOTE: Do NOT cache settings at module level here.

# ── In-memory menu cache ──────────────────────────────────
_menu_cache: Optional[Dict[str, Any]] = None
_menu_cache_timestamp: float = 0.0
MENU_CACHE_TTL: int = 600  # 10 minutes in seconds


import json
import os
from pathlib import Path

async def fetch_menu_from_api() -> Dict[str, Any]:
    """
    Fetch full menu from the local menu.txt file.
    Returns parsed JSON menu data.
    """
    # menu.txt is in the project root
    file_path = Path(__file__).parent.parent.parent / "menu.txt"
    
    if not file_path.exists():
        logger.error(f"Menu file not found at {file_path}")
        raise FileNotFoundError(f"Menu file not found at {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            raw = f.read().lstrip("\ufeff\u200b")  # Strip BOM and zero-width space
            data = json.loads(raw)
            logger.info("Menu loaded successfully from menu.txt")
            return data
    except Exception as e:
        logger.error(f"Error reading menu.txt: {e}")
        raise


async def get_menu() -> Dict[str, Any]:
    """
    Get the restaurant menu with 10-minute caching.
    Returns cached menu if still valid, otherwise fetches fresh data.
    """
    global _menu_cache, _menu_cache_timestamp

    current_time = time.time()

    if _menu_cache is not None and (current_time - _menu_cache_timestamp) < MENU_CACHE_TTL:
        logger.debug("Returning cached menu")
        return _menu_cache

    try:
        _menu_cache = await fetch_menu_from_api()
        _menu_cache_timestamp = current_time
        return _menu_cache
    except httpx.HTTPStatusError as e:
        logger.error(f"Menu API HTTP error: {e.response.status_code} - {e.response.text}")
        # Return stale cache if available
        if _menu_cache is not None:
            logger.warning("Returning stale menu cache due to API error")
            return _menu_cache
        raise
    except Exception as e:
        logger.error(f"Failed to fetch menu: {e}")
        if _menu_cache is not None:
            logger.warning("Returning stale menu cache due to error")
            return _menu_cache
        raise


def _extract_items_from_menu(menu_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract a flat list of items from the nested menu structure.
    Handles common menu data formats.
    """
    items = []

    # Try common response structures
    categories = menu_data.get("categories", menu_data.get("data", {}).get("categories", []))

    if isinstance(categories, list):
        for category in categories:
            category_items = category.get("items", [])
            for item in category_items:
                items.append(item)

    # Also check for flat item list
    if not items:
        flat_items = menu_data.get("items", menu_data.get("data", {}).get("items", []))
        if isinstance(flat_items, list):
            items = flat_items

    return items


async def validate_item(
    item_name: str, variation: Optional[str] = None
) -> Dict[str, Any]:
    """
    Validate an item exists in the menu and return its price info.
    Menu fields: itemname, variation (array), variation[].name, variation[].price
    """
    menu_data = await get_menu()
    items = menu_data.get("items", [])

    # ── Step 1: Exact item name match (case-insensitive) ──────────────────
    matched_item = None
    for item in items:
        name = item.get("itemname", "")
        if name.lower() == item_name.lower():
            matched_item = item
            break

    if matched_item is None:
        raise ValueError(
            f"Item '{item_name}' is not available on our menu."
        )

    # ── Step 3: Variation matching ─────────────────────────────────────────
    # Menu uses field "variation" (array), each entry has "name" and "price"
    variations = matched_item.get("variation", [])

    def _normalize(s: str) -> str:
        """Strip spaces and lowercase for fuzzy comparison: '1 Kg' -> '1kg'"""
        return s.replace(" ", "").lower()

    if variation and variations:
        matched_variation = None

        # Exact match first
        for var in variations:
            var_name = var.get("name", "")
            if var_name.lower() == variation.lower():
                matched_variation = var
                break

        # Fuzzy match — normalize spaces/caps (e.g. "1kg" matches "1 Kg")
        if matched_variation is None:
            for var in variations:
                var_name = var.get("name", "")
                if _normalize(var_name) == _normalize(variation):
                    matched_variation = var
                    logger.info(f"Fuzzy variation matched '{variation}' -> '{var_name}'")
                    break

        if matched_variation is None:
            available_vars = [v.get("name", "") for v in variations]
            raise ValueError(
                f"Variation '{variation}' not found for '{item_name}'. "
                f"Available: {', '.join(available_vars)}"
            )

        price = float(matched_variation.get("price", 0))
        variation = matched_variation.get("name", variation)

    elif variations and not variation:
        # Default to first variation when agent didn't specify one
        first_var = variations[0]
        variation = first_var.get("name", "Default")
        price = float(first_var.get("price", 0))
        logger.info(f"No variation for '{item_name}', defaulting to '{variation}'")

    else:
        # No variations — use item base price
        price = float(matched_item.get("price", 0))
        variation = None

    return {
        "item_name": matched_item.get("itemname", item_name),
        "variation": variation,
        "price": price,
    }


def invalidate_cache():
    """Force clear menu cache (useful for testing)."""
    global _menu_cache, _menu_cache_timestamp
    _menu_cache = None
    _menu_cache_timestamp = 0.0
    logger.info("Menu cache invalidated")


def _variation_grams(var_name: str) -> int:
    """
    Parse grams from a variation name like '1 Kg', '500 Grms', '250 Grms'.
    Returns 0 for non-weight variations (e.g., 'Pcs').
    Uses purely integer arithmetic to avoid float precision issues.
    """
    v = var_name.strip().lower()
    if "kg" in v:
        try:
            # Parse as float then convert to integer grams
            num_str = v.replace("kg", "").strip()
            # Multiply by 1000 carefully: parse integer and decimal parts separately
            if "." in num_str:
                int_part, dec_part = num_str.split(".", 1)
                dec_part = dec_part[:3].ljust(3, "0")  # pad to 3 decimal places
                return int(int_part) * 1000 + int(dec_part)
            else:
                return int(num_str) * 1000
        except (ValueError, AttributeError):
            return 0
    if "grms" in v or "grams" in v or "gm" in v:
        try:
            num_str = v.replace("grms", "").replace("grams", "").replace("gm", "").strip()
            return int(float(num_str))
        except (ValueError, AttributeError):
            return 0
    return 0


async def get_item_price_per_gram(item_name: str) -> dict:
    """
    Calculate the per-gram price for a weight-based menu item.

    Uses the largest weight-based variation as the reference to ensure
    the most representative per-gram rate (avoids rounding artifacts in
    small-pack prices).

    Returns a dict:
    {
        "price_per_gram": float,       # rupees per gram (high precision)
        "price_per_kg": float,         # price_per_gram * 1000 (easier for AI)
        "reference_variation": str,    # variation used for calculation
        "variations": [                # all weight-based variations
            {"name": str, "price": float, "grams": int, "price_per_gram": float}
        ]
    }

    Raises ValueError if item not found or has no weight-based variations.
    """
    menu_data = await get_menu()
    items = menu_data.get("items", [])

    # Find the item (case-insensitive)
    matched_item = None
    for item in items:
        if item.get("itemname", "").lower() == item_name.lower():
            matched_item = item
            break

    if matched_item is None:
        raise ValueError(f"Item '{item_name}' not found in menu.")

    variations = matched_item.get("variation", [])
    weight_variations = []

    for var in variations:
        name = var.get("name", "")
        price = float(var.get("price", 0))
        grams = _variation_grams(name)
        if grams > 0 and price > 0:
            weight_variations.append({
                "name": name,
                "price": price,
                "grams": grams,
                "price_per_gram": price / grams,
            })

    if not weight_variations:
        raise ValueError(f"Item '{item_name}' has no weight-based variations (only piece/packet variants).")

    # Select the reference variation: largest grams (most accurate per-gram rate)
    reference = max(weight_variations, key=lambda v: v["grams"])

    price_per_gram = reference["price"] / reference["grams"]

    logger.info(
        f"[PRICE] '{item_name}' — reference: {reference['name']} @ ₹{reference['price']} "
        f"/ {reference['grams']}g = ₹{price_per_gram:.6f}/g"
    )

    return {
        "price_per_gram": price_per_gram,
        "price_per_kg": price_per_gram * 1000,
        "reference_variation": reference["name"],
        "variations": weight_variations,
    }

