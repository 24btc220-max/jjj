"""
ExamGuard — /api/session router
POST /api/session/create           — create exam session
POST /api/session/{id}/start       — mark session as started
POST /api/session/{id}/end         — end session
GET  /api/session/{id}/status      — current score + violations
"""
import logging
import time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from services.session_store import store

log = logging.getLogger("examguard.routers.session")
router = APIRouter(prefix="/api/session", tags=["session"])


class CreateRequest(BaseModel):
    candidate_name: str
    exam_id: str
    duration_secs: int = 2700     # 45 minutes default
    verify_confidence: float = 0.0
    verified: bool = False


class CreateResponse(BaseModel):
    session_id: str
    candidate_name: str
    exam_id: str


class StartResponse(BaseModel):
    session_id: str
    started: bool
    start_time: float


class StatusResponse(BaseModel):
    session_id: str
    score: float
    violations: dict
    events_count: int
    elapsed_secs: int
    alert: Optional[str]


@router.post("/create", response_model=CreateResponse)
async def create_session(req: CreateRequest):
    session = store.create(req.candidate_name, req.exam_id, req.duration_secs)
    session["verified"] = req.verified
    session["verify_confidence"] = req.verify_confidence
    log.info(f"Session created: {session['id'][:8]}… for {req.candidate_name}")
    return CreateResponse(
        session_id=session["id"],
        candidate_name=req.candidate_name,
        exam_id=req.exam_id,
    )


@router.post("/{session_id}/start", response_model=StartResponse)
async def start_session(session_id: str):
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session["started"] = True
    session["start_time"] = time.time()
    log.info(f"Session {session_id[:8]}… started")
    return StartResponse(
        session_id=session_id,
        started=True,
        start_time=session["start_time"],
    )


@router.post("/{session_id}/end")
async def end_session(session_id: str):
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session["end_time"] = time.time()
    from services.monitor import close_state
    close_state(session_id)
    log.info(f"Session {session_id[:8]}… ended — final score {session['score']}")
    return {"session_id": session_id, "final_score": session["score"]}


@router.get("/{session_id}/status", response_model=StatusResponse)
async def session_status(session_id: str):
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    elapsed = int(time.time() - session["start_time"]) if session["start_time"] else 0
    return StatusResponse(
        session_id=session_id,
        score=session["score"],
        violations=dict(session["violations"]),
        events_count=len(session["events"]),
        elapsed_secs=elapsed,
        alert=store.alert_level(session_id),
    )
