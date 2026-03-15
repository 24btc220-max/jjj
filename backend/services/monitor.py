"""
ExamGuard — Frame Monitor Service
MediaPipe FaceMesh → gaze (MPIIGaze iris-to-corner ratio with Kalman)
                  → head pose (11-point 3D solvePnP)
                  → multi-face confidence voting
OpenCV fallback when MediaPipe unavailable.
"""
import base64
import logging
import math
from collections import deque

import cv2
import numpy as np

log = logging.getLogger("examguard.monitor")

# Try MediaPipe
try:
    import mediapipe as mp
    _mp_face_mesh = mp.solutions.face_mesh
    MEDIAPIPE_AVAILABLE = True
    log.info("MediaPipe available")
except Exception as e:
    MEDIAPIPE_AVAILABLE = False
    log.warning(f"MediaPipe not available: {e}")


# ── Kalman filter (1D) ─────────────────────────────────────────────────────

class Kalman1D:
    def __init__(self, Q=0.008, R=0.10):
        self.Q = Q  # process noise
        self.R = R  # measurement noise
        self.x = 0.0
        self.P = 1.0
        self.initialized = False

    def update(self, z: float) -> float:
        if not self.initialized:
            self.x = z
            self.initialized = True
            return z
        self.P += self.Q
        K = self.P / (self.P + self.R)
        self.x += K * (z - self.x)
        self.P *= (1.0 - K)
        return self.x

    def reset(self):
        self.initialized = False
        self.P = 1.0


# ── Per-session state ──────────────────────────────────────────────────────

class SessionMonitorState:
    """Holds per-session Kalman filters and calibration state."""
    def __init__(self):
        # Gaze
        self.gaze_kf_x = Kalman1D(0.006, 0.08)
        self.gaze_kf_y = Kalman1D(0.006, 0.08)
        self.gaze_baseline = None
        self.gaze_calib_samples = []
        self.GAZE_CALIB_N = 45  # Reduced from 90 for faster calibration

        # Head pose
        self.head_kf_yaw   = Kalman1D(0.012, 0.15)
        self.head_kf_pitch = Kalman1D(0.012, 0.15)
        self.head_kf_roll  = Kalman1D(0.012, 0.15)
        self.prev_yaw = 0.0
        self.prev_pitch = 0.0

        # Multi-face vote buffer
        self.multi_votes = deque(maxlen=30)

        # Face mesh instance (created once per session)
        self._mesh = None

    def get_mesh(self):
        if self._mesh is None and MEDIAPIPE_AVAILABLE:
            self._mesh = _mp_face_mesh.FaceMesh(
                max_num_faces=4,
                refine_landmarks=True,       # enables iris landmarks 468-477
                min_detection_confidence=0.60,
                min_tracking_confidence=0.60,
            )
        return self._mesh

    def close(self):
        if self._mesh:
            self._mesh.close()
            self._mesh = None


_session_states: dict[str, SessionMonitorState] = {}


def get_state(session_id: str) -> SessionMonitorState:
    if session_id not in _session_states:
        _session_states[session_id] = SessionMonitorState()
    return _session_states[session_id]


def close_state(session_id: str):
    if session_id in _session_states:
        _session_states[session_id].close()
        del _session_states[session_id]


# ── Helpers ────────────────────────────────────────────────────────────────

def _b64_to_bgr(b64: str) -> np.ndarray:
    if "," in b64:
        b64 = b64.split(",", 1)[1]
    data = base64.b64decode(b64 + "==")
    arr = np.frombuffer(data, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _iqr_median(values: list) -> float:
    s = sorted(values)
    n = len(s)
    q1 = s[n // 4]
    q3 = s[(3 * n) // 4]
    iqr = q3 - q1
    filtered = [v for v in s if q1 - 1.5*iqr <= v <= q3 + 1.5*iqr]
    return filtered[len(filtered) // 2] if filtered else s[n // 2]


def _eye_aspect_ratio(lm, eye_indices: list) -> float:
    """EAR: ratio of eye height to eye width. < 0.18 = blink."""
    p = [lm[i] for i in eye_indices]
    A = math.hypot(p[1].x - p[5].x, p[1].y - p[5].y)
    B = math.hypot(p[2].x - p[4].x, p[2].y - p[4].y)
    C = math.hypot(p[0].x - p[3].x, p[0].y - p[3].y) + 1e-8
    return (A + B) / (2.0 * C)


# ── Gaze analysis ──────────────────────────────────────────────────────────

def _analyze_gaze(lm, state: SessionMonitorState) -> dict:
    """
    ENHANCED: MPIIGaze iris-to-corner ratio with aggressive extreme eye detection.
    Detects when eyes look extremely left/right/down while head is in correct position.
    Returns detailed gaze metrics for accurate eye movement detection.
    """
    if len(lm) < 478:
        return {"calibrating": True, "deviated": False, "zone": "no_iris"}

    # Blink detection — skip gaze during blinks
    left_ear  = _eye_aspect_ratio(lm, [33, 160, 158, 133, 153, 144])
    right_ear = _eye_aspect_ratio(lm, [362, 385, 387, 263, 373, 380])
    avg_ear = (left_ear + right_ear) / 2
    if avg_ear < 0.18:
        return {"blink": True, "deviated": False, "zone": "blink", "ear": round(avg_ear, 3)}

    # Iris landmark indices
    li, ri = lm[468], lm[473]
    lo, li2, lt, lb = lm[33], lm[133], lm[159], lm[145]
    ro, ri2, rt, rb = lm[263], lm[362], lm[386], lm[374]

    def safe_div(a, b):
        return a / b if abs(b) > 1e-5 else 0.5

    # Raw horizontal gaze (0-1 scale: 0=left, 0.5=center, 1=right)
    lgx = safe_div(li.x - lo.x, li2.x - lo.x)
    rgx = safe_div(ri.x - ri2.x, ro.x - ri2.x)
    lgy = safe_div(li.y - lt.y,  lb.y  - lt.y)
    rgy = safe_div(ri.y - rt.y,  rb.y  - rt.y)

    raw_gx = (lgx + rgx) / 2
    raw_gy = (lgy + rgy) / 2

    # Detect eye invisibility (iris outside eye bounds)
    left_iris_visible  = -0.1 < lgx < 1.1
    right_iris_visible = -0.1 < rgx < 1.1
    both_visible = left_iris_visible and right_iris_visible
    
    # Calibration phase (collect baseline)
    if state.gaze_baseline is None:
        if both_visible:
            state.gaze_calib_samples.append({"x": raw_gx, "y": raw_gy})
        n = len(state.gaze_calib_samples)
        if n >= state.GAZE_CALIB_N:
            xs = [s["x"] for s in state.gaze_calib_samples]
            ys = [s["y"] for s in state.gaze_calib_samples]
            state.gaze_baseline = {
                "x": _iqr_median(xs),
                "y": _iqr_median(ys),
            }
        return {"calibrating": True, "deviated": False, "zone": f"calibrating {n}/{state.GAZE_CALIB_N}"}

    gx = state.gaze_kf_x.update(raw_gx)
    gy = state.gaze_kf_y.update(raw_gy)

    dx = gx - state.gaze_baseline["x"]
    dy = gy - state.gaze_baseline["y"]

    # ENHANCED: More aggressive thresholds for extreme eye movements
    # Eyes moving far left/right (even with head straight) = suspicious
    H_THR_EXTREME = 0.32   # iris very far left/right
    H_THR_NORMAL = 0.20    # normal threshold (more strict than before)
    V_THR_EXTREME = 0.28   # iris very far up/down
    V_THR_NORMAL = 0.18    # normal vertical threshold

    # Check for extreme eye positions
    iris_far_left  = raw_gx < 0.25
    iris_far_right = raw_gx > 0.75
    iris_far_down  = raw_gy > 0.75
    
    go_left  = dx < -H_THR_NORMAL
    go_right = dx >  H_THR_NORMAL
    go_up    = dy < -V_THR_NORMAL
    go_down  = dy >  V_THR_NORMAL

    # Thinking exemption (looking up without horizontal deviation)
    thinking_up = go_up and abs(dx) < 0.05

    # Determine zone with aggressive extreme eye detection
    zone = "center"
    deviated = False

    # AGGRESSIVE: Flag extreme eye positions regardless of baseline comparison
    if iris_far_left and not iris_far_right:
        zone = "extreme_left"
        deviated = True
    elif iris_far_right and not iris_far_left:
        zone = "extreme_right"
        deviated = True
    elif iris_far_down:
        zone = "extreme_down"
        deviated = True
    # Standard deviation-based zones
    elif thinking_up:
        zone = "thinking_up"
        deviated = False
    elif go_up and go_left:
        zone = "up_left"
        deviated = True
    elif go_up and go_right:
        zone = "up_right"
        deviated = True
    elif go_down and go_left:
        zone = "down_left"
        deviated = True
    elif go_down and go_right:
        zone = "down_right"
        deviated = True
    elif go_left:
        zone = "left"
        deviated = True
    elif go_right:
        zone = "right"
        deviated = True
    elif go_down:
        zone = "down"
        deviated = True
    else:
        zone = "center"
        deviated = False

    # Eyes not visible at edges = definitely suspicious
    if not both_visible:
        deviated = True
        if raw_gx < 0.3:
            zone = "extreme_left_invisible"
        elif raw_gx > 0.7:
            zone = "extreme_right_invisible"
        else:
            zone = "invisible"

    return {
        "deviated": deviated,
        "zone": zone,
        "dx": round(float(dx), 4),
        "dy": round(float(dy), 4),
        "gx": round(float(gx), 4),  # Absolute iris position (for debugging)
        "gy": round(float(gy), 4),
        "ear": round(avg_ear, 3),
        "calibrated": True,
        "visible": both_visible,
    }


# ── Head pose analysis ─────────────────────────────────────────────────────

# 3D model reference points (mm, AFLW/Basel Face Model)
_MODEL_3D = np.array([
    [  0.0,    0.0,   0.0],   # nose tip        lm[4]
    [  0.0,  -63.6, -12.5],   # chin            lm[152]
    [-43.3,   32.7, -26.0],   # L-eye outer     lm[33]
    [ 43.3,   32.7, -26.0],   # R-eye outer     lm[263]
    [-28.9,  -28.9, -24.1],   # L-mouth         lm[61]
    [ 28.9,  -28.9, -24.1],   # R-mouth         lm[291]
    [-55.0,    0.0, -40.0],   # L-cheek         lm[234]
    [ 55.0,    0.0, -40.0],   # R-cheek         lm[454]
    [-17.5,   34.0, -16.5],   # L-eye inner     lm[133]
    [ 17.5,   34.0, -16.5],   # R-eye inner     lm[362]
    [  0.0,   63.0, -20.0],   # forehead        lm[10]
], dtype=np.float64)

_LM_IDX = [4, 152, 33, 263, 61, 291, 234, 454, 133, 362, 10]


def _analyze_head(lm, state: SessionMonitorState, img_w: int, img_h: int) -> dict:
    """
    IMPROVED: Detects head position relative to FRAME BOUNDARIES.
    Instead of absolute rotation angles, checks if face landmarks are near frame edges.
    
    Frame safety zone: [0.2, 0.8] on both axes
    - Going to 0.2 or 0.8 = getting close to edges = suspicious
    - Outside [0.15, 0.85] = TOO CLOSE or out of frame = critical
    
    Also returns head pose angles for reference + visualization.
    """
    pts2d = np.array(
        [[lm[i].x * img_w, lm[i].y * img_h] for i in _LM_IDX],
        dtype=np.float64
    )

    # Camera intrinsics approximation (focal length = image width)
    focal = img_w
    cam_matrix = np.array([
        [focal, 0, img_w / 2],
        [0, focal, img_h / 2],
        [0, 0, 1],
    ], dtype=np.float64)
    dist_coeffs = np.zeros((4, 1))

    success, rvec, tvec = cv2.solvePnP(
        _MODEL_3D, pts2d, cam_matrix, dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not success:
        return {"suspicious": False, "yaw": 0, "pitch": 0, "roll": 0, "frame_status": "ok"}

    rmat, _ = cv2.Rodrigues(rvec)
    # Decompose rotation matrix to Euler angles
    sy = math.sqrt(rmat[0,0]**2 + rmat[1,0]**2)
    singular = sy < 1e-6
    if not singular:
        pitch_r = math.atan2(rmat[2,1], rmat[2,2])
        yaw_r   = math.atan2(-rmat[2,0], sy)
        roll_r  = math.atan2(rmat[1,0], rmat[0,0])
    else:
        pitch_r = math.atan2(-rmat[1,2], rmat[1,1])
        yaw_r   = math.atan2(-rmat[2,0], sy)
        roll_r  = 0.0

    raw_yaw   = math.degrees(yaw_r)
    raw_pitch = math.degrees(pitch_r)
    raw_roll  = math.degrees(roll_r)

    yaw   = state.head_kf_yaw.update(raw_yaw)
    pitch = state.head_kf_pitch.update(raw_pitch)
    roll  = state.head_kf_roll.update(raw_roll)

    # FRAME BOUNDARY DETECTION ──────────────────────────────────────────────
    # Check if facial landmarks are drifting toward frame edges
    
    # Key landmarks for position check: left-most, right-most, top, bottom of face
    face_points_norm = [[lm[i].x, lm[i].y] for i in _LM_IDX]
    
    x_coords = [p[0] for p in face_points_norm]
    y_coords = [p[1] for p in face_points_norm]
    
    x_min, x_max = min(x_coords), max(x_coords)
    y_min, y_max = min(y_coords), max(y_coords)
    
    # Safety zones:
    # NORMAL: x in [0.25, 0.75], y in [0.25, 0.75]
    # WARNING: x in [0.15, 0.85], y in [0.15, 0.85]  ← getting close to edges
    # CRITICAL: outside [0.10, 0.90] ← near or out of frame
    
    NORMAL_MIN, NORMAL_MAX = 0.25, 0.75
    WARNING_MIN, WARNING_MAX = 0.15, 0.85
    CRITICAL_MIN, CRITICAL_MAX = 0.10, 0.90
    
    # Determine frame status
    frame_status = "ok"
    boundary_violated = False
    boundary_detail = ""
    
    # Check X axis (horizontal)
    if x_min < CRITICAL_MIN or x_max > CRITICAL_MAX:
        frame_status = "out_of_frame"
        boundary_violated = True
        if x_min < CRITICAL_MIN:
            boundary_detail += "left_edge_critical "
        if x_max > CRITICAL_MAX:
            boundary_detail += "right_edge_critical "
    elif x_min < WARNING_MIN or x_max > WARNING_MAX:
        frame_status = "too_close_edge"
        boundary_violated = True
        if x_min < WARNING_MIN:
            boundary_detail += "left_edge_warning "
        if x_max > WARNING_MAX:
            boundary_detail += "right_edge_warning "
    
    # Check Y axis (vertical)
    if y_min < CRITICAL_MIN or y_max > CRITICAL_MAX:
        if frame_status == "ok":
            frame_status = "out_of_frame"
        boundary_violated = True
        if y_min < CRITICAL_MIN:
            boundary_detail += "top_edge_critical "
        if y_max > CRITICAL_MAX:
            boundary_detail += "bottom_edge_critical "
    elif y_min < WARNING_MIN or y_max > WARNING_MAX:
        if frame_status == "ok":
            frame_status = "too_close_edge"
        boundary_violated = True
        if y_min < WARNING_MIN:
            boundary_detail += "top_edge_warning "
        if y_max > WARNING_MAX:
            boundary_detail += "bottom_edge_warning "
    
    # Velocity check for sudden jerky movements
    vel_yaw   = abs(yaw   - state.prev_yaw)
    vel_pitch = abs(pitch - state.prev_pitch)
    state.prev_yaw   = yaw
    state.prev_pitch = pitch
    sudden = vel_yaw > 8 or vel_pitch > 6
    
    # SUSPICION LEVELS:
    # - Boundary violation = clearly suspicious
    # - Extreme angles (old logic) only if ALSO going out of frame
    # - Sudden movements = worth flagging
    suspicious = boundary_violated or sudden

    return {
        "suspicious": suspicious,
        "sudden": sudden,
        "yaw":   round(yaw, 1),
        "pitch": round(pitch, 1),
        "roll":  round(roll, 1),
        "vel_yaw":   round(vel_yaw, 1),
        "vel_pitch": round(vel_pitch, 1),
        "frame_status": frame_status,
        "frame_detail": boundary_detail.strip(),
        "x_min": round(x_min, 3),
        "x_max": round(x_max, 3),
        "y_min": round(y_min, 3),
        "y_max": round(y_max, 3),
    }


# ── Multi-face analysis ────────────────────────────────────────────────────

def _analyze_multi(face_list: list, state: SessionMonitorState,
                   img_w: int, img_h: int) -> dict:
    """
    Confidence-weighted multi-face detection with area filter.
    Requires >60% vote in 30-frame window for 2 faces,
    immediate flag for 3+ faces.
    """
    frame_area = img_w * img_h

    valid_faces = []
    for lm_set in face_list:
        lm = lm_set.landmark
        # Area filter: face must occupy ≥0.5% of frame
        xs = [lm[234].x, lm[454].x]
        ys = [lm[10].y,  lm[152].y]
        fw = abs(xs[1] - xs[0]) * img_w
        fh = abs(ys[1] - ys[0]) * img_h
        if (fw * fh) / frame_area >= 0.005:
            valid_faces.append(lm_set)

    count = len(valid_faces)
    state.multi_votes.append(1 if count > 1 else 0)
    vote_ratio = sum(state.multi_votes) / max(len(state.multi_votes), 1)

    immediate = count >= 3
    sustained = (count == 2) and (vote_ratio > 0.60)
    suspicious = immediate or sustained

    return {
        "count": count,
        "suspicious": suspicious,
        "immediate": immediate,
        "vote_ratio": round(vote_ratio, 3),
    }


# ── Main frame analysis entry point ────────────────────────────────────────

def analyze_frame(frame_b64: str, session_id: str) -> dict:
    """
    Full frame analysis: face count, gaze, head pose.
    Returns structured dict consumed by the scoring engine.
    Includes visualization data (landmarks, iris, head vectors) for frontend drawing.
    """
    state = get_state(session_id)
    result = {
        "face_count": 0,
        "gaze": {},
        "head": {},
        "multi": {},
        "error": None,
        "visualization": {  # NEW: data for frontend visualization
            "landmarks": [],
            "iris": [],
            "head_direction": [],
        }
    }

    try:
        img_bgr = _b64_to_bgr(frame_b64)
        if img_bgr is None:
            result["error"] = "Could not decode frame"
            return result

        h, w = img_bgr.shape[:2]
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

        mesh = state.get_mesh()
        if mesh is None:
            result["error"] = "MediaPipe not available"
            return result

        mesh_result = mesh.process(img_rgb)
        faces = mesh_result.multi_face_landmarks or []
        result["face_count"] = len(faces)

        # Multi-face
        if faces:
            result["multi"] = _analyze_multi(faces, state, w, h)

        # Primary face analysis (first/largest face)
        if len(faces) > 0:
            lm = faces[0].landmark
            result["gaze"] = _analyze_gaze(lm, state)
            result["head"] = _analyze_head(lm, state, w, h)
            
            # VISUALIZATION DATA ────────────────────────────────────────────
            # Key facial landmarks for mesh drawing (every 10th point)
            vis_landmarks = []
            for i in range(0, min(468, len(lm)), 10):
                vis_landmarks.append({
                    "x": round(lm[i].x, 4),
                    "y": round(lm[i].y, 4),
                    "z": round(lm[i].z, 4),
                    "idx": i,
                })
            result["visualization"]["landmarks"] = vis_landmarks
            
            # Iris landmarks (468-477) for gaze visualization
            if len(lm) > 477:
                iris_data = []
                for iris_idx in [468, 469, 470, 471, 472, 473, 474, 475, 476, 477]:
                    if iris_idx < len(lm):
                        iris_data.append({
                            "x": round(lm[iris_idx].x, 4),
                            "y": round(lm[iris_idx].y, 4),
                            "z": round(lm[iris_idx].z, 4),
                            "side": "left" if iris_idx < 473 else "right",
                        })
                result["visualization"]["iris"] = iris_data
            
            # Head direction (from nose to forehead) — simplified head pose visualization
            if len(lm) > 10:
                nose = {"x": lm[4].x, "y": lm[4].y}  # nose tip
                forehead = {"x": lm[10].x, "y": lm[10].y}  # forehead
                chin = {"x": lm[152].x, "y": lm[152].y}  # chin
                result["visualization"]["head_direction"] = [
                    {"from": nose, "to": forehead, "label": "pitch"},
                    {"from": nose, "to": chin, "label": "vertical"},
                ]

    except Exception as e:
        log.error(f"analyze_frame error: {e}")
        result["error"] = str(e)

    return result


# ── OpenCV fallback (no MediaPipe) ─────────────────────────────────────────

_haar_face = None

def analyze_frame_fallback(frame_b64: str) -> dict:
    """OpenCV Haar cascade fallback — face count only, no gaze/head."""
    global _haar_face
    try:
        if _haar_face is None:
            _haar_face = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
        img = _b64_to_bgr(frame_b64)
        if img is None:
            return {"face_count": 0}
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        faces = _haar_face.detectMultiScale(gray, 1.1, 5, minSize=(50, 50))
        return {"face_count": len(faces), "fallback": True}
    except Exception as e:
        return {"face_count": 0, "error": str(e)}
