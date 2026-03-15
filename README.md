# ExamGuard Pro — Full Stack AI Exam Integrity System

## Project Structure

```
examguard/
├── backend/
│   ├── main.py                  ← FastAPI app entry point
│   ├── requirements.txt         ← Python dependencies
│   ├── routers/
│   │   ├── verify.py            ← POST /api/verify/identity
│   │   ├── session.py           ← Session create/start/end
│   │   ├── monitor.py           ← Frame/audio/tab + WebSocket /ws/{id}
│   │   └── report.py            ← GET /api/report/{id}
│   └── services/
│       ├── identity.py          ← DeepFace ArcFace/VGG-Face verification
│       ├── monitor.py           ← MediaPipe gaze + head pose + multi-face
│       ├── speech.py            ← Whisper STT + scipy VAD (F0+Mel+ZCR)
│       └── session_store.py     ← In-memory session + scoring engine
└── frontend/
    └── index.html               ← Full UI (connects to backend via WebSocket)
```

---

## Setup in VS Code

### Step 1 — Open in VS Code
```
File → Open Folder → select the examguard/ folder
```

### Step 2 — Create Python virtual environment
```bash
# In VS Code terminal (Ctrl+`)
cd backend
python -m venv venv

# Activate it:
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate
```

### Step 3 — Install dependencies
```bash
pip install -r requirements.txt
```

> **Note on heavy packages:**
> - `deepface` downloads model weights (~500MB) on first use
> - `openai-whisper` downloads the `base` model (~150MB) on first use
> - `torch` is ~2GB — be patient on first install
>
> **Minimal install** (if you want to skip DeepFace/Whisper):
> ```bash
> pip install fastapi uvicorn[standard] python-multipart websockets pydantic opencv-python mediapipe numpy scipy Pillow
> ```
> The system will gracefully fall back to OpenCV and VAD-only mode.

### Step 4 — Run the backend
```bash
# From the backend/ directory with venv activated:
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

### Step 5 — Open the frontend
Install the **Live Server** extension in VS Code (by Ritwick Dey), then:
- Open `frontend/index.html`
- Right-click → **Open with Live Server**
- Opens at `http://127.0.0.1:5500/frontend/index.html`

Or simply open `frontend/index.html` directly in Chrome/Edge.

### Step 6 — Use Chrome or Edge
The Web Speech API (real-time speech transcription) only works in Chrome or Edge.

---

## How it works

### Backend (FastAPI)
| Endpoint | Description |
|----------|-------------|
| `GET /health` | Check which AI libraries are loaded |
| `POST /api/verify/identity` | DeepFace face comparison (ID vs webcam) |
| `POST /api/session/create` | Create exam session, returns session_id |
| `POST /api/session/{id}/start` | Mark session as started |
| `WS /ws/{session_id}` | Real-time bidirectional: receives frames+audio, sends analysis |
| `POST /api/monitor/tab/{id}` | Tab switch event |
| `GET /api/report/{id}` | Full integrity report |
| `GET /docs` | Interactive API documentation (Swagger UI) |

### Frontend
- Connects to backend on load, shows connection status
- Falls back to **client-side AI** (MediaPipe + VAD) if backend unavailable
- When backend is connected: sends frames via WebSocket at ~10fps, receives scores + events
- Speech: dual-layer — browser VAD + Web Speech API transcript → sent to backend

### AI Detection Modules
| Module | Technology | What it detects |
|--------|-----------|----------------|
| Identity | DeepFace (ArcFace/VGG-Face) | ID document vs webcam face comparison |
| Gaze | MediaPipe iris (lm 468/473) + Kalman filter | Looking left/right/up/down from screen |
| Head Pose | 11-point 3D solvePnP (OpenCV) | Yaw/Pitch/Roll angles |
| Multi-face | MediaPipe maxNumFaces=4 + vote buffer | Extra person in frame |
| Voice (VAD) | scipy FFT: F0 autocorrelation + 13-band Mel + ZCR | Human voice vs ambient noise |
| Voice (STT) | OpenAI Whisper base + keyword detection | Spoken exam answers |
| Tab switch | Page Visibility API | Browser tab/window focus loss |

---

## API docs
After starting the backend, visit: `http://localhost:8000/docs`

This gives you the full interactive Swagger UI to test every endpoint.

---

## Environment Variables (optional)
Create `backend/.env`:
```
EXAMGUARD_PORT=8000
WHISPER_MODEL=base        # tiny / base / small / medium / large
DEEPFACE_MODEL=ArcFace    # ArcFace / VGG-Face / Facenet
```

---

## Troubleshooting

**Backend won't start:**
- Make sure venv is activated before running uvicorn
- Try `pip install --upgrade fastapi uvicorn` if import errors

**DeepFace error on first run:**
- It downloads weights on first call — wait ~30s and try again
- Or use the minimal install (OpenCV fallback) for testing

**MediaPipe error:**
- Install `mediapipe==0.10.14` specifically: `pip install mediapipe==0.10.14`

**Speech not detected:**
- Must use Chrome or Edge (Firefox does not support Web Speech API)
- Allow microphone permission when prompted

**Face verification fails:**
- Use a clear, well-lit ID photo
- Capture webcam in good lighting, facing directly at camera
- DeepFace with `enforce_detection=False` handles lower-quality ID card photos
