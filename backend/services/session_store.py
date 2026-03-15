"""
ExamGuard — Session Store
Thread-safe in-memory session management + scoring engine
"""
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime
from typing import Optional


class SessionStore:
    def __init__(self):
        self._sessions: dict = {}
        self._lock = threading.Lock()

    # ── Create / Get ──────────────────────────────────────────────────────────

    def create(self, candidate_name: str, exam_id: str, duration_secs: int = 2700) -> dict:
        sid = str(uuid.uuid4())
        session = {
            "id": sid,
            "candidate_name": candidate_name,
            "exam_id": exam_id,
            "duration_secs": duration_secs,
            "score": 100.0,
            "verified": False,
            "verify_confidence": 0.0,
            "started": False,
            "start_time": None,
            "end_time": None,
            "events": [],
            "violations": defaultdict(int),
            "score_history": [{"t": 0, "s": 100}],
            "penalties_total": defaultdict(int),
            "cooldowns": {},           # violation_key → last_triggered_time
            "frame_buffer": deque(maxlen=30),
            "tab_switches": 0,
            "total_idle_secs": 0,
            "tab_away_start": None,
            "speech_transcripts": [],
            "screenshots": [],
            # rolling buffers for sustained-event detection
            "_face_buf": 0,
            "_gaze_buf": 0,
            "_head_buf": 0,
            "_multi_buf": deque(maxlen=30),   # votes: 1=multi, 0=single
        }
        with self._lock:
            self._sessions[sid] = session
        return session

    def get(self, sid: str) -> Optional[dict]:
        return self._sessions.get(sid)

    def all_ids(self) -> list:
        return list(self._sessions.keys())

    # ── Scoring ───────────────────────────────────────────────────────────────

    # Base penalties (research-calibrated)
    PENALTIES = {
        "face_exit":     {"base": 12, "priority": "P2", "cooldown": 3.5},
        "gaze_diversion":{"base": 7,  "priority": "P3", "cooldown": 3.5},
        "head_movement": {"base": 6,  "priority": "P3", "cooldown": 3.5},
        "multi_face":    {"base": 20, "priority": "P1", "cooldown": 3.5},
        "voice_detected":{"base": 8,  "priority": "P2", "cooldown": 2.5},
        "tab_switch":    {"base": 10, "priority": "P2", "cooldown": 1.0},
    }

    def penalize(self, sid: str, violation: str, custom_amount: float = None,
                 detail: str = "") -> Optional[dict]:
        session = self.get(sid)
        if not session or not session["started"]:
            return None

        cfg = self.PENALTIES.get(violation, {"base": 5, "priority": "P3", "cooldown": 3.0})
        now = time.time()

        # Cooldown check
        last = session["cooldowns"].get(violation, 0)
        if now - last < cfg["cooldown"]:
            return None

        session["cooldowns"][violation] = now

        # Frequency escalation multiplier — repeated violations cost more
        count = session["violations"][violation] + 1
        session["violations"][violation] = count
        freq_mult = min(1 + 0.20 * (count - 1), 2.5)

        # Duration weight for tab switches
        if violation == "tab_switch" and session.get("_last_idle_secs", 0) > 0:
            idle = session["_last_idle_secs"]
            dur_weight = min(1 + (idle / 30), 2.0)
        else:
            dur_weight = 1.0

        amount = custom_amount or min(round(cfg["base"] * freq_mult * dur_weight), 25)
        session["score"] = max(0.0, session["score"] - amount)
        session["penalties_total"][violation] += amount

        # Build event record
        elapsed = round(time.time() - session["start_time"]) if session["start_time"] else 0
        minutes, secs = divmod(elapsed, 60)
        event = {
            "event_type": violation,
            "label": self._label(violation, detail),
            "penalty": amount,
            "occurrence": count,
            "priority": cfg["priority"],
            "time": f"{minutes:02d}:{secs:02d}",
            "score_after": round(session["score"], 1),
            "detail": f"Event #{count} ×{freq_mult:.1f} escalation",
            "timestamp": datetime.now().isoformat(),
        }
        session["events"].append(event)

        # Score history
        session["score_history"].append({"t": elapsed, "s": round(session["score"], 1)})

        return event

    @staticmethod
    def _label(vtype: str, detail: str) -> str:
        base = {
            "face_exit":      "Face exited frame",
            "gaze_diversion": "Gaze diversion detected",
            "head_movement":  "Head pose violation",
            "multi_face":     "Multiple faces detected",
            "voice_detected": "Voice/speech detected",
            "tab_switch":     "Tab switch / focus lost",
        }.get(vtype, vtype)
        return f"{base}{' — ' + detail if detail else ''}"

    # ── Alerts ────────────────────────────────────────────────────────────────

    def alert_level(self, sid: str) -> Optional[str]:
        session = self.get(sid)
        if not session:
            return None
        s = session["score"]
        if s <= 55:
            return "terminated"
        if s <= 80:
            return "warning"
        return None


# Singleton
store = SessionStore()
