"""
Script to push prompt.txt and menu.txt to the MongoDB config collection.
Run this script whenever you update the local text files to propagate changes to the DB.

    python scripts/push_config.py

To pull content back from DB into local files, import this module and call:

    import asyncio
    from scripts.push_config import pull_prompt_from_db, pull_menu_from_db

    asyncio.run(pull_prompt_from_db())   # DB → prompt.txt
    asyncio.run(pull_menu_from_db())     # DB → menu.txt
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import db_instance, connect_to_mongo, close_mongo_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# PUSH  (local files → MongoDB)
# ──────────────────────────────────────────────────────────────────────────────

async def push_configs():
    """Push prompt.txt and menu.txt to the MongoDB config collection."""
    try:
        await connect_to_mongo()
        db = db_instance.db
        if db is None:
            logger.error("Failed to connect to MongoDB.")
            return

        project_root = Path(__file__).parent.parent

        # 1. Push Prompt
        prompt_path = project_root / "prompt.txt"
        if prompt_path.exists():
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_content = f.read()

            await db["config"].update_one(
                {"type": "prompt"},
                {"$set": {"content": prompt_content}},
                upsert=True
            )
            logger.info("Successfully pushed prompt.txt to DB.")
        else:
            logger.warning("prompt.txt not found.")

        # 2. Push Menu
        menu_path = project_root / "menu.txt"
        if menu_path.exists():
            with open(menu_path, "r", encoding="utf-8-sig") as f:
                raw_menu = f.read().lstrip("\ufeff\u200b")
                menu_data = json.loads(raw_menu)

            await db["config"].update_one(
                {"type": "menu"},
                {"$set": {"data": menu_data}},
                upsert=True
            )
            logger.info("Successfully pushed menu.txt to DB.")
        else:
            logger.warning("menu.txt not found.")

    except Exception as e:
        logger.error(f"Error pushing configs: {e}")
    finally:
        await close_mongo_connection()


# ──────────────────────────────────────────────────────────────────────────────
# PULL  (MongoDB → local files)   — importable library functions
# ──────────────────────────────────────────────────────────────────────────────

async def pull_prompt_from_db():
    """
    Pull the prompt from MongoDB and overwrite local prompt.txt.

    Usage (from another script):
        import asyncio
        from scripts.push_config import pull_prompt_from_db
        asyncio.run(pull_prompt_from_db())
    """
    try:
        await connect_to_mongo()
        db = db_instance.db
        if db is None:
            logger.error("Failed to connect to MongoDB.")
            return

        config_doc = await db["config"].find_one({"type": "prompt"})
        if not config_doc or "content" not in config_doc:
            logger.warning("No prompt document found in DB.")
            return

        prompt_content = config_doc["content"]
        project_root = Path(__file__).parent.parent
        prompt_path = project_root / "prompt.txt"
        print(prompt_path)
        print(prompt_content)

        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(prompt_content)
        logger.info(f"Successfully pulled prompt from DB → {prompt_path}")

    except Exception as e:
        logger.error(f"Error pulling prompt: {e}")
    finally:
        await close_mongo_connection()


async def pull_menu_from_db():
    """
    Pull the menu from MongoDB and overwrite local menu.txt (pretty-printed JSON).

    Usage (from another script):
        import asyncio
        from scripts.push_config import pull_menu_from_db
        asyncio.run(pull_menu_from_db())
    """
    try:
        await connect_to_mongo()
        db = db_instance.db
        if db is None:
            logger.error("Failed to connect to MongoDB.")
            return

        config_doc = await db["config"].find_one({"type": "menu"})
        if not config_doc or "data" not in config_doc:
            logger.warning("No menu document found in DB.")
            return

        menu_data = config_doc["data"]
        project_root = Path(__file__).parent.parent
        menu_path = project_root / "menu.txt"

        with open(menu_path, "w", encoding="utf-8") as f:
            json.dump(menu_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Successfully pulled menu from DB → {menu_path}")

    except Exception as e:
        logger.error(f"Error pulling menu: {e}")
    finally:
        await close_mongo_connection()


# ──────────────────────────────────────────────────────────────────────────────
# Entry point — runs PUSH only (same as before)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    asyncio.run(push_configs())
