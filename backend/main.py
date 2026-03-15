"""
ExamGuard Pro — FastAPI Backend
Run with: uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""
import logging
import os
import sys
from pathlib import Path

# Ensure backend/ is on the path so "from routers import ..." always works
_BACKEND_DIR = Path(__file__).parent.resolve()
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from routers import verify, session, monitor, report

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("examguard")

# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ExamGuard Pro API",
    description="AI-powered online exam integrity monitoring backend",
    version="5.0.0",
)

# ── CORS — allow frontend dev server ────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # restrict to your frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(verify.router)
app.include_router(session.router)
app.include_router(monitor.router)
app.include_router(report.router)

# ── Serve frontend ────────────────────────────────────────────────────────────
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

@app.get("/", include_in_schema=False)
async def serve_frontend_root():
    """Serve index.html at root"""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")
    return {"message": "ExamGuard Pro API v5.0 running. Frontend not found.", "docs": "/docs"}

# Mount static files (CSS, JS, images if any)
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health():
    """Quick health check — returns dependency status."""
    status = {"api": "ok"}

    try:
        import mediapipe  # noqa
        status["mediapipe"] = "ok"
    except ImportError:
        status["mediapipe"] = "not installed"

    try:
        from deepface import DeepFace  # noqa
        status["deepface"] = "ok"
    except ImportError:
        status["deepface"] = "not installed — using OpenCV fallback"

    try:
        import whisper  # noqa
        status["whisper"] = "ok"
    except ImportError:
        status["whisper"] = "not installed — VAD only"

    try:
        import cv2  # noqa
        status["opencv"] = cv2.__version__
    except ImportError:
        status["opencv"] = "not installed"

    return status


# ── Dev entrypoint ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
