"""
ExamGuard — Identity Verification Service
Uses DeepFace (VGG-Face / ArcFace) for 128-dim face descriptor comparison.
Falls back to OpenCV ORB + histogram when DeepFace is unavailable.
"""
import base64
import io
import logging
import numpy as np

log = logging.getLogger("examguard.identity")

# Try importing DeepFace — graceful fallback if not installed
try:
    from deepface import DeepFace
    DEEPFACE_AVAILABLE = True
    log.info("DeepFace loaded successfully")
except ImportError:
    DEEPFACE_AVAILABLE = False
    log.warning("DeepFace not installed — using OpenCV fallback")

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


def _b64_to_numpy(b64: str) -> np.ndarray:
    """Decode base64 image string to numpy BGR array."""
    import cv2
    # Strip data URL prefix if present
    if "," in b64:
        b64 = b64.split(",", 1)[1]
    data = base64.b64decode(b64 + "==")
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


def _numpy_to_tmp_file(img: np.ndarray, suffix: str) -> str:
    """Save numpy image to a temp file and return the path."""
    import tempfile, os
    import cv2
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="examguard_")
    os.close(fd)
    cv2.imwrite(path, img)
    return path


# ── DeepFace verification ──────────────────────────────────────────────────

def verify_with_deepface(id_b64: str, webcam_b64: str) -> dict:
    """
    Compare two face images using DeepFace.
    Returns dict: {match, confidence, distance, model, detail, error?}
    
    Models tried in order: ArcFace (most accurate) → VGG-Face → Facenet
    Distance metric: cosine similarity
    Threshold: ArcFace cosine ≤ 0.68 = same person
    """
    import os
    tmp1 = tmp2 = None
    try:
        img1 = _b64_to_numpy(id_b64)
        img2 = _b64_to_numpy(webcam_b64)

        if img1 is None:
            return {"match": False, "confidence": 0, "error": "Could not decode ID document image"}
        if img2 is None:
            return {"match": False, "confidence": 0, "error": "Could not decode webcam image"}

        tmp1 = _numpy_to_tmp_file(img1, ".jpg")
        tmp2 = _numpy_to_tmp_file(img2, ".jpg")

        # Try ArcFace first (state-of-art), fall back to VGG-Face
        for model in ["ArcFace", "VGG-Face", "Facenet"]:
            try:
                result = DeepFace.verify(
                    img1_path=tmp1,
                    img2_path=tmp2,
                    model_name=model,
                    distance_metric="cosine",
                    enforce_detection=False,   # allow low-quality ID card photos
                    detector_backend="opencv",
                )
                dist = float(result["distance"])
                threshold = float(result["threshold"])
                match = result["verified"]

                # Convert distance → confidence percentage
                # cosine distance 0 = identical, threshold ~0.40-0.68 = match boundary
                confidence = round(max(0, (1 - dist / (threshold * 2))) * 100, 1)

                return {
                    "match": match,
                    "confidence": confidence,
                    "distance": round(dist, 4),
                    "threshold": round(threshold, 4),
                    "model": model,
                    "detail": f"{model} cosine distance: {dist:.4f} (threshold ≤ {threshold:.4f})"
                }
            except Exception as e:
                log.warning(f"DeepFace {model} failed: {e} — trying next model")
                continue

        return {"match": False, "confidence": 0, "error": "All DeepFace models failed"}

    except Exception as e:
        log.error(f"verify_with_deepface error: {e}")
        return {"match": False, "confidence": 0, "error": str(e)}
    finally:
        for p in [tmp1, tmp2]:
            if p:
                try:
                    os.remove(p)
                except Exception:
                    pass


# ── OpenCV fallback verification ───────────────────────────────────────────

def verify_with_opencv(id_b64: str, webcam_b64: str) -> dict:
    """
    Fallback: ORB feature matching + RGB histogram cosine similarity.
    Less accurate than DeepFace but requires no ML models.
    """
    import cv2
    try:
        img1 = _b64_to_numpy(id_b64)
        img2 = _b64_to_numpy(webcam_b64)

        if img1 is None or img2 is None:
            return {"match": False, "confidence": 0, "error": "Could not decode images"}

        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

        def extract_face(img):
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
            faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(50, 50))
            if len(faces) == 0:
                # Use center crop as fallback
                h, w = img.shape[:2]
                roi = img[int(h*0.1):int(h*0.9), int(w*0.15):int(w*0.85)]
            else:
                x, y, fw, fh = max(faces, key=lambda f: f[2]*f[3])
                roi = img[y:y+fh, x:x+fw]
            return cv2.resize(roi, (128, 128))

        face1 = extract_face(img1)
        face2 = extract_face(img2)

        # ORB feature matching
        orb = cv2.ORB_create(nfeatures=800)
        kp1, d1 = orb.detectAndCompute(cv2.cvtColor(face1, cv2.COLOR_BGR2GRAY), None)
        kp2, d2 = orb.detectAndCompute(cv2.cvtColor(face2, cv2.COLOR_BGR2GRAY), None)

        orb_score = 0.0
        if d1 is not None and d2 is not None and len(d1) > 10 and len(d2) > 10:
            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
            matches = sorted(bf.match(d1, d2), key=lambda m: m.distance)
            good = [m for m in matches if m.distance < 55]
            orb_score = min(len(good) / max(len(matches) * 0.30, 1), 1.0)

        # Color histogram cosine similarity
        def hist_cos(a, b):
            ha = cv2.calcHist([a], [0, 1, 2], None, [8, 8, 8], [0,256]*3).flatten()
            hb = cv2.calcHist([b], [0, 1, 2], None, [8, 8, 8], [0,256]*3).flatten()
            cv2.normalize(ha, ha)
            cv2.normalize(hb, hb)
            dot = float(np.dot(ha, hb))
            norm = float(np.linalg.norm(ha) * np.linalg.norm(hb)) + 1e-8
            return max(0.0, dot / norm)

        hist_score = hist_cos(face1, face2)

        combined = orb_score * 0.55 + hist_score * 0.45
        confidence = round(combined * 100, 1)

        return {
            "match": confidence >= 35,
            "confidence": confidence,
            "model": "OpenCV ORB+Histogram (fallback)",
            "detail": f"ORB: {orb_score*100:.1f}% · Histogram: {hist_score*100:.1f}%",
        }

    except Exception as e:
        log.error(f"verify_with_opencv error: {e}")
        return {"match": False, "confidence": 0, "error": str(e)}


# ── Public API ─────────────────────────────────────────────────────────────

def verify_identity(id_b64: str, webcam_b64: str) -> dict:
    """
    Main entry point: uses DeepFace if available, otherwise OpenCV fallback.
    """
    if DEEPFACE_AVAILABLE:
        return verify_with_deepface(id_b64, webcam_b64)
    elif CV2_AVAILABLE:
        log.info("Using OpenCV fallback for face verification")
        return verify_with_opencv(id_b64, webcam_b64)
    else:
        return {
            "match": True,
            "confidence": 70,
            "model": "No backend (demo mode)",
            "detail": "Install deepface or opencv-python for real verification",
        }
