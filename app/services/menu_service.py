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
settings = get_settings()

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
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
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

    Args:
        item_name: Name of the item to validate.
        variation: Optional variation (e.g., "Half", "Full").

    Returns:
        Dict with keys: item_name, variation, price

    Raises:
        ValueError: If item or variation is not found.
    """
    menu_data = await get_menu()
    items = _extract_items_from_menu(menu_data)

    # Find matching item (case-insensitive)
    matched_item = None
    for item in items:
        name = item.get("name", item.get("item_name", ""))
        if name.lower() == item_name.lower():
            matched_item = item
            break

    if matched_item is None:
        available = [
            item.get("name", item.get("item_name", ""))
            for item in items
        ]
        raise ValueError(
            f"Item '{item_name}' not found in menu. "
            f"Available items: {', '.join(available[:10])}"
        )

    # Determine price
    variations = matched_item.get("variations", matched_item.get("options", []))

    if variation and variations:
        # Find matching variation
        matched_variation = None
        for var in variations:
            var_name = var.get("name", var.get("variation_name", ""))
            if var_name.lower() == variation.lower():
                matched_variation = var
                break

        if matched_variation is None:
            available_vars = [
                v.get("name", v.get("variation_name", ""))
                for v in variations
            ]
            raise ValueError(
                f"Variation '{variation}' not found for '{item_name}'. "
                f"Available variations: {', '.join(available_vars)}"
            )

        price = float(matched_variation.get("price", 0))
    elif variations and not variation:
        # Default to first variation if no variation specified
        first_var = variations[0]
        variation = first_var.get("name", first_var.get("variation_name", "Default"))
        price = float(first_var.get("price", 0))
        logger.info(f"No variation specified for '{item_name}', defaulting to '{variation}'")
    else:
        # No variations — use item price directly
        price = float(matched_item.get("price", matched_item.get("item_price", 0)))

    return {
        "item_name": matched_item.get("name", matched_item.get("item_name", item_name)),
        "variation": variation,
        "price": price,
    }


def invalidate_cache():
    """Force clear menu cache (useful for testing)."""
    global _menu_cache, _menu_cache_timestamp
    _menu_cache = None
    _menu_cache_timestamp = 0.0
    logger.info("Menu cache invalidated")
