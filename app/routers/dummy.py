import logging
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Dummy Tool"])

class DummyRequest(BaseModel):
    message: str
    session_id: str

class DummyResponse(BaseModel):
    status: str
    reply: str

@router.post("/dummy", response_model=DummyResponse)
async def dummy_tool(request: DummyRequest):
    """
    A dummy tool endpoint for testing Rock8 AI function calling.
    The agent can send a message and a session_id, and it returns a success reply.
    """
    logger.info(f"Dummy tool called with message: '{request.message}' for session: '{request.session_id}'")
    return DummyResponse(
        status="success",
        reply=f"Dummy tool successfully processed the message: {request.message}"
    )
