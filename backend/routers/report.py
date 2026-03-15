"""
ExamGuard — /api/report router
GET /api/report/{session_id}  — full structured integrity report
"""
import logging
import time
from fastapi import APIRouter, HTTPException

from services.session_store import store

log = logging.getLogger("examguard.routers.report")
router = APIRouter(prefix="/api/report", tags=["report"])


@router.get("/{session_id}")
async def get_report(session_id: str):
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    elapsed = 0
    if session["start_time"]:
        end = session.get("end_time") or time.time()
        elapsed = int(end - session["start_time"])

    minutes, secs = divmod(elapsed, 60)
    final_score = round(session["score"], 1)

    # Verdict
    if final_score <= 30:
        verdict = "DISQUALIFIED"
    elif final_score <= 60:
        verdict = "SUSPENDED"
    elif final_score <= 80:
        verdict = "BORDERLINE"
    else:
        verdict = "LEGITIMATE"

    # Per-module summary
    penalties = dict(session.get("penalties_total", {}))
    violations = dict(session["violations"])

    modules = {
        "multi_face": {
            "name": "Multiple Faces",
            "priority": "P1",
            "events": violations.get("multi_face", 0),
            "total_penalty": penalties.get("multi_face", 0),
        },
        "face_exit": {
            "name": "Frame Exit",
            "priority": "P2",
            "events": violations.get("face_exit", 0),
            "total_penalty": penalties.get("face_exit", 0),
        },
        "voice_detected": {
            "name": "Voice / Speech (VAD + Whisper)",
            "priority": "P2",
            "events": violations.get("voice_detected", 0),
            "total_penalty": penalties.get("voice_detected", 0),
        },
        "tab_switch": {
            "name": "Tab Switch",
            "priority": "P2",
            "events": violations.get("tab_switch", 0),
            "total_penalty": penalties.get("tab_switch", 0),
        },
        "gaze_diversion": {
            "name": "Gaze Diversion (MPIIGaze + Kalman)",
            "priority": "P3",
            "events": violations.get("gaze_diversion", 0),
            "total_penalty": penalties.get("gaze_diversion", 0),
        },
        "head_movement": {
            "name": "Head Pose (11-pt solvePnP)",
            "priority": "P3",
            "events": violations.get("head_movement", 0),
            "total_penalty": penalties.get("head_movement", 0),
        },
    }

    # AI conclusion
    total_events = len([e for e in session["events"] if e.get("penalty", 0) > 0])
    crit_events = sum(1 for e in session["events"] if e.get("priority") == "P1" and e.get("penalty", 0) > 0)
    speech_events = violations.get("voice_detected", 0)
    tab_events = violations.get("tab_switch", 0)

    if final_score > 80:
        conclusion = (
            f"Candidate {session['candidate_name']} completed exam {session['exam_id']} "
            f"with integrity score {final_score}/100. Identity was "
            f"{'verified at ' + str(round(session.get('verify_confidence',0),1)) + '% confidence' if session.get('verified') else 'not verified'}. "
            f"No significant anomalies detected. Recommendation: VALID."
        )
        tags = ["CLEAN SESSION", "VALID", "ID VERIFIED"]
    elif final_score > 70:
        conclusion = (
            f"Score {final_score}/100 — {total_events} minor event(s). "
            f"Recommendation: Provisionally valid — manual review advised."
        )
        tags = ["WARNING", "REVIEW RECOMMENDED"]
    elif final_score > 50:
        conclusion = (
            f"Score {final_score}/100 — {total_events} events including {crit_events} P1-critical, "
            f"{speech_events} speech, {tab_events} tab-switch. "
            f"Recommendation: FLAGGED — disciplinary review required."
        )
        tags = ["FLAGGED", "HIGH SUSPICION", "SPEECH DETECTED"]
    else:
        conclusion = (
            f"Terminated at {final_score}/100 — {total_events} violations: "
            f"{crit_events} P1-critical, {speech_events} speech, {tab_events} tab-switch. "
            f"Recommendation: DISQUALIFIED. Results invalid."
        )
        tags = ["DISQUALIFIED", "INVALID", "CRITICAL VIOLATIONS"]

    return {
        "session_id": session_id,
        "candidate_name": session["candidate_name"],
        "exam_id": session["exam_id"],
        "date": session["start_time"],
        "duration_secs": elapsed,
        "duration_display": f"{minutes}m {secs}s",
        "final_score": final_score,
        "verdict": verdict,
        "verified": session.get("verified", False),
        "verify_confidence": session.get("verify_confidence", 0.0),
        "tab_switches": session.get("tab_switches", 0),
        "total_idle_secs": session.get("total_idle_secs", 0),
        "speech_transcripts": session.get("speech_transcripts", []),
        "modules": modules,
        "events": [e for e in session["events"] if e.get("penalty", 0) > 0],
        "score_history": session["score_history"],
        "conclusion": conclusion,
        "tags": tags,
    }
