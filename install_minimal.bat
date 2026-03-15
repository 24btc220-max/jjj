@echo off
title ExamGuard Pro — Minimal Install
color 0A

echo.
echo  =========================================================
echo   EXAMGUARD PRO — Minimal Install (no DeepFace/Whisper)
echo   Installs in ~2 minutes. Full install takes ~15 minutes.
echo  =========================================================
echo.

cd /d "%~dp0backend"

if not exist "venv\Scripts\activate.bat" (
    python -m venv venv
)
call venv\Scripts\activate.bat

echo  Installing minimal dependencies...
pip install fastapi==0.111.0 uvicorn[standard]==0.30.1 python-multipart==0.0.9 websockets==12.0 pydantic==2.7.1 opencv-python mediapipe numpy scipy Pillow aiofiles

echo.
echo  Done! Run start.bat to launch the server.
echo  (Face verification will use OpenCV fallback instead of DeepFace)
echo  (Voice will use VAD-only instead of Whisper transcription)
echo.
pause
