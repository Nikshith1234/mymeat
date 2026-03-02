"""
Rightside router — endpoint to configure inbound calling via Rightside AI.
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.services.rightside_service import configure_inbound, build_rightside_payload

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Rightside"])


class RightsideResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None


@router.post("/rightside/sync", response_model=RightsideResponse)
async def sync_rightside():
    """
    Push Meatcraft configuration (prompt + tools) to Rightside AI.
    Call this once to set up the inbound number, or again to update.
    """
    try:
        data = await configure_inbound()
        return RightsideResponse(
            success=True,
            message="Rightside inbound configured successfully!",
            data=data
        )
    except Exception as e:
        logger.error(f"Sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rightside/preview")
async def preview_payload():
    """Preview the payload that will be sent to Rightside (for debugging)."""
    try:
        payload = await build_rightside_payload()
        return payload
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
