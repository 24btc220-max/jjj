"""
ExamGuard — /api/monitor router + WebSocket
POST /api/monitor/frame/{session_id}      — analyze single frame
POST /api/monitor/audio/{session_id}      — analyze audio chunk
POST /api/monitor/tab/{session_id}        — tab switch event
POST /api/monitor/screenshot/{session_id} — tab-away screenshot

WS   /ws/{session_id}                     — real-time bidirectional channel
  Client → Server:
    {type: "frame",  data: "<base64 jpeg>"}
    {type: "audio",  samples: [...], sample_rate: 16000}
    {type: "ping"}
  Server → Client:
    {type: "analysis", score, face_count, gaze, head, multi, events_fired, alert}
    {type: "pong"}
    {type: "error",  message}
"""
import asyncio
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from services.session_store import store
from services import monitor as mon_svc
from services import speech as spc_svc

log = logging.getLogger("examguard.routers.monitor")
router = APIRouter(tags=["monitor"])

# Frame analysis thresholds (buffer counts before triggering penalty)
FACE_BUF_THRESH  = 40    # ~2s at 20fps
GAZE_BUF_THRESH  = 20    # ~1s at 20fps — MORE AGGRESSIVE (was 45)
HEAD_BUF_THRESH  = 50
HEAD_SUDDEN_THRESH = 20  # lower for sudden movement
MULTI_IMMEDIATE  = True  # instant for 3+ faces
VAD_THRESH       = 25    # frames of sustained speech


# ── REST endpoints ──────────────────────────────────────────────────────────

class FrameRequest(BaseModel):
    frame_b64: str


class AudioRequest(BaseModel):
    samples: list[float]
    sample_rate: int = 16000


class TabRequest(BaseModel):
    action: str            # "left" | "returned"
    idle_secs: int = 0


@router.post("/api/monitor/frame/{session_id}")
async def analyze_frame_endpoint(session_id: str, req: FrameRequest):
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await asyncio.get_event_loop().run_in_executor(
        None, mon_svc.analyze_frame, req.frame_b64, session_id
    )
    events = _process_frame_result(result, session_id)
    return {
        "analysis": result,
        "events_fired": events,
        "score": session["score"],
        "alert": store.alert_level(session_id),
    }


@router.post("/api/monitor/audio/{session_id}")
async def analyze_audio_endpoint(session_id: str, req: AudioRequest):
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    vad = spc_svc.score_vad(req.samples, req.sample_rate, session_id)
    events = []
    if vad["is_speech"]:
        ev = store.penalize(session_id, "voice_detected", detail=f"F0:{vad['pitch']}Hz SNR:{vad['snr']}x")
        if ev:
            events.append(ev)
    return {"vad": vad, "events_fired": events, "score": session["score"]}


@router.post("/api/monitor/tab/{session_id}")
async def tab_event(session_id: str, req: TabRequest):
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    events = []
    if req.action == "left":
        session["tab_switches"] += 1
        session["tab_away_start"] = time.time()
        log.info(f"Session {session_id[:8]}… tab left (switch #{session['tab_switches']})")

    elif req.action == "returned" and session.get("tab_away_start"):
        idle = req.idle_secs or int(time.time() - session["tab_away_start"])
        session["total_idle_secs"] = session.get("total_idle_secs", 0) + idle
        session["tab_away_start"] = None
        session["_last_idle_secs"] = idle
        # Logarithmic penalty: 5s=~3pts, 30s=~10pts, 60s+=~15pts, cap 20
        import math
        penalty = min(round(10 * (1 + math.log(1 + idle / 10))), 20)
        ev = store.penalize(session_id, "tab_switch",
                            custom_amount=penalty,
                            detail=f"Away {idle}s")
        if ev:
            events.append(ev)

    return {
        "action": req.action,
        "events_fired": events,
        "score": session["score"],
        "tab_switches": session.get("tab_switches", 0),
    }


@router.post("/api/monitor/screenshot/{session_id}")
async def save_screenshot(session_id: str, req: FrameRequest):
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    elapsed = int(time.time() - session["start_time"]) if session["start_time"] else 0
    m, s = divmod(elapsed, 60)
    session["screenshots"].append({
        "time": f"{m:02d}:{s:02d}",
        "timestamp": elapsed,
        "data": req.frame_b64,  # Store full base64 for display in report
        "reason": "tab-away"           # Can be extended for other reasons
    })
    return {"saved": True, "count": len(session["screenshots"])}


# ── WebSocket ────────────────────────────────────────────────────────────────

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    Real-time bidirectional WebSocket for the exam session.
    Receives frames + audio from client, sends back analysis + events.
    """
    session = store.get(session_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()
    log.info(f"WebSocket connected for session {session_id[:8]}…")

    # Per-session buffer counters
    buf = {
        "face": 0,
        "gaze": 0,
        "head": 0,
        "vad": 0,
    }

    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                continue

            msg_type = msg.get("type")

            # ── Ping/pong ──
            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            # ── Frame analysis ──
            if msg_type == "frame":
                frame_b64 = msg.get("data", "")
                if not frame_b64:
                    continue

                # Run analysis in thread pool (CPU-bound)
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, mon_svc.analyze_frame, frame_b64, session_id
                )

                events_fired = _process_frame_result(result, session_id, buf)
                alert = store.alert_level(session_id)

                payload = {
                    "type": "analysis",
                    "score": round(session["score"], 1),
                    "face_count": result.get("face_count", 0),
                    "gaze": result.get("gaze", {}),
                    "head": result.get("head", {}),
                    "multi": result.get("multi", {}),
                    "events_fired": events_fired,
                    "alert": {"type": alert, "score": session["score"]} if alert else None,
                }
                await websocket.send_text(json.dumps(payload))

            # ── Audio analysis ──
            elif msg_type == "audio":
                samples = msg.get("samples", [])
                sr = msg.get("sample_rate", 16000)
                if not samples:
                    continue

                loop = asyncio.get_event_loop()
                vad = await loop.run_in_executor(
                    None, spc_svc.score_vad, samples, sr, session_id
                )

                events_fired = []
                if vad["is_speech"]:
                    buf["vad"] += 1
                    if buf["vad"] >= VAD_THRESH:
                        ev = store.penalize(session_id, "voice_detected",
                                            detail=f"F0:{vad['pitch']}Hz SNR:{vad['snr']}x")
                        if ev:
                            events_fired.append(ev)
                            buf["vad"] = 0
                else:
                    buf["vad"] = max(0, buf["vad"] - 1)

                if events_fired:
                    await websocket.send_text(json.dumps({
                        "type": "analysis",
                        "score": round(session["score"], 1),
                        "events_fired": events_fired,
                        "vad": vad,
                        "alert": None,
                    }))

            # ── Speech transcript (from Web Speech API on frontend) ──
            elif msg_type == "transcript":
                text = msg.get("text", "")
                suspicious = msg.get("suspicious", False)
                if text and suspicious:
                    session["speech_transcripts"].append({
                        "text": text,
                        "suspicious": suspicious,
                        "time": msg.get("time", ""),
                    })
                    # Only penalize if VAD also confirmed speech recently
                    if buf["vad"] > 3:
                        ev = store.penalize(session_id, "voice_detected",
                                            detail=f'Speech: "{text[:30]}…"')
                        if ev:
                            await websocket.send_text(json.dumps({
                                "type": "analysis",
                                "score": round(session["score"], 1),
                                "events_fired": [ev],
                                "alert": None,
                            }))

            # ── Tab event ──
            elif msg_type == "tab":
                action = msg.get("action")
                idle_secs = msg.get("idle_secs", 0)
                events_fired = []
                if action == "left":
                    session["tab_switches"] = session.get("tab_switches", 0) + 1
                    session["tab_away_start"] = time.time()
                elif action == "returned":
                    if session.get("tab_away_start"):
                        idle = idle_secs or int(time.time() - session["tab_away_start"])
                        session["total_idle_secs"] = session.get("total_idle_secs", 0) + idle
                        session["tab_away_start"] = None
                        session["_last_idle_secs"] = idle
                        import math
                        penalty = min(round(10 * (1 + math.log(1 + idle / 10))), 20)
                        ev = store.penalize(session_id, "tab_switch",
                                            custom_amount=penalty,
                                            detail=f"Away {idle}s")
                        if ev:
                            events_fired.append(ev)

                if events_fired or action == "left":
                    await websocket.send_text(json.dumps({
                        "type": "analysis",
                        "score": round(session["score"], 1),
                        "events_fired": events_fired,
                        "alert": {"type": store.alert_level(session_id), "score": session["score"]}
                                 if store.alert_level(session_id) else None,
                    }))

    except WebSocketDisconnect:
        log.info(f"WebSocket disconnected for session {session_id[:8]}…")
    except Exception as e:
        log.error(f"WebSocket error for {session_id[:8]}: {e}")
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass


# ── Frame result processor ──────────────────────────────────────────────────

def _process_frame_result(result: dict, session_id: str,
                           buf: Optional[dict] = None) -> list:
    """
    Convert frame analysis result into score penalties.
    Returns list of events fired.
    """
    if buf is None:
        buf = {"face": 0, "gaze": 0, "head": 0}

    events = []
    face_count = result.get("face_count", 0)
    gaze = result.get("gaze", {})
    head = result.get("head", {})
    multi = result.get("multi", {})

    # ── Face absence ──
    if face_count == 0:
        buf["face"] = buf.get("face", 0) + 1
        if buf["face"] >= FACE_BUF_THRESH:
            ev = store.penalize(session_id, "face_exit", detail="No face detected")
            if ev:
                events.append(ev)
                buf["face"] = 0
    else:
        buf["face"] = max(0, buf.get("face", 0) - 3)

    # ── Multi-face ──
    if multi.get("suspicious"):
        ev = store.penalize(session_id, "multi_face",
                            detail=f"{face_count} faces (vote: {multi.get('vote_ratio',0):.0%})")
        if ev:
            events.append(ev)

    # ── Gaze ──
    if gaze.get("deviated") and not gaze.get("blink") and not gaze.get("calibrating"):
        buf["gaze"] = buf.get("gaze", 0) + 1
        threshold = GAZE_BUF_THRESH
        if buf["gaze"] >= threshold:
            ev = store.penalize(session_id, "gaze_diversion",
                                detail=f"Zone: {gaze.get('zone','unknown')}")
            if ev:
                events.append(ev)
                buf["gaze"] = 0
    else:
        buf["gaze"] = max(0, buf.get("gaze", 0) - 2)

    # ── Head pose ──
    if head.get("suspicious"):
        buf["head"] = buf.get("head", 0) + 1
        threshold = HEAD_SUDDEN_THRESH if head.get("sudden") else HEAD_BUF_THRESH
        if buf["head"] >= threshold:
            ev = store.penalize(
                session_id, "head_movement",
                detail=f"Yaw:{head.get('yaw',0)}° Pitch:{head.get('pitch',0)}° Roll:{head.get('roll',0)}°"
            )
            if ev:
                events.append(ev)
                buf["head"] = 0
    else:
        buf["head"] = max(0, buf.get("head", 0) - 2)

    return events
