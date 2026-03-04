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
    Uses 'itemname', 'variationname', 'price' fields from menu.txt.
    """
    menu_data = await get_menu()
    items = menu_data.get("items", [])

    # Find matching item (case-insensitive, field: "itemname")
    matched_item = None
    for item in items:
        name = item.get("itemname", "")
        if name.lower() == item_name.lower():
            matched_item = item
            break

    if matched_item is None:
        # Fuzzy fallback: check if item_name is a substring
        for item in items:
            name = item.get("itemname", "")
            if item_name.lower() in name.lower() or name.lower() in item_name.lower():
                matched_item = item
                logger.info(f"Fuzzy matched '{item_name}' -> '{name}'")
                break

    if matched_item is None:
        available = [item.get("itemname", "") for item in items[:10]]
        raise ValueError(
            f"Item '{item_name}' not found in menu. "
            f"Some available: {', '.join(available)}"
        )

    # Determine price — menu.txt uses "variations" list with "variationname" and "price"
    variations = matched_item.get("variations", [])

    if variation and variations:
        matched_variation = None
        for var in variations:
            var_name = var.get("variationname", var.get("name", ""))
            if var_name.lower() == variation.lower():
                matched_variation = var
                break

        if matched_variation is None:
            available_vars = [v.get("variationname", v.get("name", "")) for v in variations]
            raise ValueError(
                f"Variation '{variation}' not found for '{item_name}'. "
                f"Available: {', '.join(available_vars)}"
            )

        price = float(matched_variation.get("price", 0))
        variation = matched_variation.get("variationname", variation)
    elif variations and not variation:
        # Default to first variation
        first_var = variations[0]
        variation = first_var.get("variationname", first_var.get("name", "Default"))
        price = float(first_var.get("price", 0))
        logger.info(f"No variation specified for '{item_name}', defaulting to '{variation}'")
    else:
        # No variations — use item price directly
        price = float(matched_item.get("price", matched_item.get("item_price", 0)))
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
