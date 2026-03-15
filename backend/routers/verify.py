"""
ExamGuard — /api/verify router
POST /api/verify/identity   — compare ID photo vs webcam face
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.identity import verify_identity

log = logging.getLogger("examguard.routers.verify")
router = APIRouter(prefix="/api/verify", tags=["verify"])


class VerifyRequest(BaseModel):
    id_photo_b64: str      # base64 of ID document image
    webcam_b64: str        # base64 of live webcam capture
    session_id: str = ""   # optional — to attach verification result to session


class VerifyResponse(BaseModel):
    match: bool
    confidence: float
    model: str
    detail: str
    error: str = ""


@router.post("/identity", response_model=VerifyResponse)
async def verify_identity_endpoint(req: VerifyRequest):
    """
    Compare ID document face vs live webcam face.
    Uses DeepFace (ArcFace/VGG-Face) if available, OpenCV ORB fallback otherwise.
    """
    if not req.id_photo_b64 or not req.webcam_b64:
        raise HTTPException(status_code=400, detail="id_photo_b64 and webcam_b64 are required")

    result = verify_identity(req.id_photo_b64, req.webcam_b64)
    log.info(f"Identity verification: match={result.get('match')} conf={result.get('confidence')}%")

    return VerifyResponse(
        match=result.get("match", False),
        confidence=result.get("confidence", 0.0),
        model=result.get("model", "unknown"),
        detail=result.get("detail", ""),
        error=result.get("error", ""),
    )
