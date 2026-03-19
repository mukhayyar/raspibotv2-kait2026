# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PENS-KAIT 2026 is a robot control web dashboard for a Yahboom Raspbot running on Raspberry Pi 5. It provides real-time browser-based control (movement, servos, LEDs, buzzer) with live camera feed and YOLO object detection, all communicated over Socket.IO.

## Architecture

**Backend** (`backend/`): Python Flask + Flask-SocketIO server (`app.py`). Single-file server handling:
- Robot hardware control via `Raspbot_Lib` (I2C/SMBus) — gracefully degrades to mock mode when hardware unavailable
- Camera capture thread (CSI via `rpicam-vid` subprocess or USB via OpenCV)
- YOLO inference thread (ultralytics) with dynamic model/class switching
- Phase 1 scene recognition (`models/phase1_model.py`) using Places365 GoogLeNet (Caffe via OpenCV DNN)
- Context management (`context_manager.py`) — SQLite DB mapping scene names to YOLO classes, seeded from Places365 CSV
- Session-based password authentication, access logging to SQLite (`data/access.db`)
- MJPEG streaming endpoints (`/video_feed`, `/video_feed_research`, `/video_feed_raw`)

**Frontend** (`frontend/`): React 19 + Vite 7 SPA. Components in `src/components/`. Single custom hook `src/hooks/useSocket.js` manages all Socket.IO state. No router — single page with control dashboard.

**Communication**: Socket.IO events for all real-time control (move, stop, servo, speed, led, buzzer, detection_toggle, detection_config, set_scene, etc.). Frontend proxies `/socket.io` and `/video_feed` to backend:5000 in dev mode via Vite config.

**Alternative backends** (`backend_cpp/`, `backend_rust/`): Experimental C++/Rust implementations for performance testing. Not the primary backend.

## Commands

### Docker (production deployment)
```bash
sudo docker compose up --build        # Build and run both services
sudo docker compose up -d             # Run detached
sudo docker compose down              # Stop
```
Backend runs on port 5000, frontend (nginx) on port 3000.

### Backend (local development)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                  # Edit .env to set ADMIN_PASSWORD, CAMERA_TYPE
python app.py                         # Starts on http://0.0.0.0:5000
```

### Frontend (local development)
```bash
cd frontend
npm install
npm run dev                           # Vite dev server on http://0.0.0.0:5173 (proxies to backend:5000)
npm run build                         # Production build to dist/
npm run lint                          # ESLint
```

## Key Design Decisions

- **Threading model**: Camera capture, YOLO inference, sensor polling, status broadcast, and system monitoring all run as separate daemon threads. Shared state protected by `state_lock`, `detection_lock`, `auth_lock`, `_db_lock`.
- **Camera abstraction**: `LibCameraCapture` class wraps `rpicam-vid` subprocess (YUV420 pipe) for Pi 5 CSI cameras. Falls back to OpenCV `VideoCapture(0)` for USB cameras. Controlled by `CAMERA_TYPE` env var.
- **YOLO model switching**: Supports hot-swapping models at runtime via `set_scene` Socket.IO event. YOLOWorld models (`*worldv2*`) support dynamic `set_classes()`; standard YOLO models use fixed built-in classes. Model files go in `backend/models/`.
- **Auth**: Simple session-based password auth over Socket.IO. `ADMIN_PASSWORD` from `.env`. All motor/LED/buzzer commands require auth; camera feeds and research page do not.
- **Docker privileges**: Container runs with `privileged: true` and `/dev` mounted for I2C and camera hardware access. Entrypoint script (`entrypoint.sh`) sets device permissions.

## Environment Variables (backend/.env)

- `ADMIN_PASSWORD` — dashboard unlock password
- `CAMERA_TYPE` — `AUTO`, `CSI`, or `USB`
- `TURNSTILE_SECRET_KEY`, `TURNSTILE_SITE_KEY` — Cloudflare Turnstile (optional)

## Platform

Target hardware is Raspberry Pi 5 running Raspberry Pi OS (Bookworm). The backend uses `smbus2` with a shim for `Raspbot_Lib` compatibility. Docker images are built for `linux/arm64`.
