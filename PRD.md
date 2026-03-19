# Product Requirements Document (PRD)

## PENS-KAIT 2026 — Context-Aware Robot Control Dashboard

**Version**: 1.0
**Date**: 2026-03-09
**Authors**: PENS-KAIT Joint Research Team (Politeknik Elektronika Negeri Surabaya & Kanagawa Institute of Technology)

---

## 1. Problem Statement

Researchers and operators controlling mobile robots remotely need a unified interface that combines real-time motor/sensor control with intelligent object detection that automatically adapts to the robot's environment. Existing solutions treat teleoperation and computer vision as separate concerns, requiring manual reconfiguration of detection models and classes when the robot moves between different scenes (e.g., from a kitchen to an outdoor parking lot).

## 2. Product Vision

A browser-based dashboard that enables real-time control of a Yahboom Raspbot (Raspberry Pi 5) while providing **context-aware object detection** — a multi-phase pipeline where scene recognition automatically selects the optimal YOLO model and detection classes for the robot's current environment.

## 3. Target Users

| User | Needs |
|------|-------|
| **Researchers** | Evaluate detection models, benchmark inference performance across formats (PyTorch, ONNX, TFLite), study context-switching behavior |
| **Operators** | Remotely drive the robot, monitor sensors, view live camera feed with detection overlays |
| **Demonstrators** | Showcase the system at exhibitions/conferences via public URL (Cloudflare Tunnel) or YouTube livestream |

## 4. Target Platform

- **Hardware**: Yahboom Raspbot with Raspberry Pi 5 (4GB/8GB), CSI camera module, ultrasonic sensor, IR receiver, 4x line-tracking sensors, 2x servos (pan/tilt), WS2812 LEDs, buzzer, 4WD motor driver over I2C
- **OS**: Raspberry Pi OS Bookworm (aarch64)
- **Deployment**: Docker Compose (backend + frontend containers), privileged mode for hardware access

## 5. Functional Requirements

### 5.1 Real-Time Robot Control

| ID | Requirement | Priority |
|----|------------|----------|
| RC-1 | 8-directional movement (forward, backward, left, right, and 4 diagonals) via keyboard (WASD/arrows) and on-screen D-pad | P0 |
| RC-2 | Pan/tilt servo control via keyboard (IJKL) and on-screen D-pad with continuous hold-to-move | P0 |
| RC-3 | Adjustable motor speed (0–255) with keyboard presets (1/2/3) and slider | P0 |
| RC-4 | LED control: on/off, preset colors, and RGB brightness adjustment | P1 |
| RC-5 | Buzzer toggle | P1 |
| RC-6 | Emergency stop via Space/Escape key | P0 |
| RC-7 | Mobile-friendly touch controls: floating D-pads for movement (left) and servo (right) with haptic feedback | P0 |
| RC-8 | Combo key support — pressing two directional keys simultaneously produces diagonal movement | P1 |

### 5.2 Live Camera Feed

| ID | Requirement | Priority |
|----|------------|----------|
| CF-1 | MJPEG stream from CSI camera (via rpicam-vid/libcamera subprocess) or USB camera (OpenCV) | P0 |
| CF-2 | Auto-detection of camera type (CSI → USB fallback), configurable via `CAMERA_TYPE` env var | P0 |
| CF-3 | Three stream endpoints: `/video_feed` (with detection overlay when enabled), `/video_feed_research` (always with overlay), `/video_feed_raw` (no overlay) | P1 |
| CF-4 | FPS overlay on captured frames | P2 |
| CF-5 | Graceful "Camera Offline" placeholder when no camera is available | P1 |

### 5.3 Object Detection (YOLO)

| ID | Requirement | Priority |
|----|------------|----------|
| OD-1 | Toggle YOLO detection on/off from the dashboard | P0 |
| OD-2 | Adjustable confidence threshold (0.05–1.0) via slider | P0 |
| OD-3 | Dynamic class editing — user can type comma-separated class names and apply (YOLOWorld models only) | P1 |
| OD-4 | Real-time detection results displayed as class name + count in the Detection Panel | P0 |
| OD-5 | Bounding box overlays drawn on the MJPEG stream with per-class color coding | P0 |
| OD-6 | Support multiple model formats: PyTorch (.pt), ONNX (.onnx), TFLite (.tflite) via ultralytics | P1 |
| OD-7 | Model export utility (`backend/models/change_format_model.py`) for converting between formats | P2 |

### 5.4 Context-Aware Detection (Multi-Phase Pipeline)

| ID | Requirement | Priority |
|----|------------|----------|
| CA-1 | **Phase 1 — Scene Recognition**: Places365 GoogLeNet (Caffe) classifies the camera frame into one of 365 scene categories (e.g., "kitchen", "parking_lot") | P1 |
| CA-2 | **Phase 2 — Context Switching**: Scene name triggers a database lookup (`context_manager.py`) that returns the appropriate YOLO model file and detection classes for that scene | P1 |
| CA-3 | **Runtime model hot-swap**: When a scene requires a different model file, load it without restarting the server | P1 |
| CA-4 | Scene-to-class mapping database (SQLite), auto-seeded from Places365 CSV with heuristic class assignment | P1 |
| CA-5 | Manual scene override via `set_scene` Socket.IO event | P2 |
| CA-6 | CRUD API for scene contexts: get all, save/update (via Socket.IO events `get_all_contexts`, `save_context`) | P2 |

### 5.5 Sensor Monitoring

| ID | Requirement | Priority |
|----|------------|----------|
| SM-1 | Ultrasonic distance sensor display (mm) with color-coded danger/warning thresholds (<100mm red, <300mm yellow) | P0 |
| SM-2 | 4-channel line-tracking sensor visualization | P1 |
| SM-3 | IR remote value display | P2 |
| SM-4 | Sensor data pushed to all clients via Socket.IO at ~3Hz | P0 |

### 5.6 System Monitoring

| ID | Requirement | Priority |
|----|------------|----------|
| SY-1 | Real-time CPU usage, RAM usage, and CPU temperature display | P1 |
| SY-2 | Camera FPS counter | P1 |
| SY-3 | System stats broadcast at 1Hz to all connected clients | P1 |

### 5.7 Authentication & Security

| ID | Requirement | Priority |
|----|------------|----------|
| AU-1 | Password-based unlock via Socket.IO (ADMIN_PASSWORD from .env) | P0 |
| AU-2 | All motor/LED/buzzer/detection commands gated behind authentication | P0 |
| AU-3 | Camera feeds and research page accessible without authentication | P1 |
| AU-4 | Access logging to SQLite: connect, disconnect, auth success/failure events with IP and session ID | P1 |
| AU-5 | UI shows locked/unlocked state; controls grayed out when locked | P0 |

### 5.8 Research Dashboard

| ID | Requirement | Priority |
|----|------------|----------|
| RD-1 | Separate `/research` page with always-on detection overlay and Phase 1 scene results | P1 |
| RD-2 | Research mode activates inference thread even when main dashboard detection is disabled | P1 |
| RD-3 | Servo control available without authentication on research page | P2 |

### 5.9 Deployment & Streaming

| ID | Requirement | Priority |
|----|------------|----------|
| DP-1 | Docker Compose deployment with backend (Python) and frontend (nginx) containers | P0 |
| DP-2 | Cloudflare Tunnel integration for public access without port forwarding (systemd service provided) | P2 |
| DP-3 | YouTube livestream support via Xvfb + Chromium + FFmpeg pipeline (`livestream_youtube.sh`) with automatic 12-hour segmentation for VOD archival | P2 |

## 6. Non-Functional Requirements

| ID | Requirement | Target |
|----|------------|--------|
| NF-1 | Control latency (keypress to motor actuation) | < 100ms on LAN |
| NF-2 | Camera stream frame rate | 30 FPS capture, 30 FPS stream |
| NF-3 | YOLO inference speed (yolo26n, 320px input) | ~20ms per frame target (currently ~300–460ms on CPU, motivating C++/Rust backends) |
| NF-4 | Concurrent WebSocket clients | At least 5 simultaneous viewers |
| NF-5 | Graceful degradation | System runs in mock mode without hardware; camera/YOLO/Phase1 each fail independently |
| NF-6 | Memory footprint | < 1.5GB RSS for backend process |

## 7. Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    Browser (React SPA)                        │
│  ┌──────────┐ ┌──────────┐ ┌────────────┐ ┌──────────────┐  │
│  │ D-Pad    │ │ Camera   │ │ Detection  │ │ Sensor/Status│  │
│  │ Controls │ │ Feed     │ │ Panel      │ │ Panels       │  │
│  └────┬─────┘ └────┬─────┘ └─────┬──────┘ └──────┬───────┘  │
│       │ Socket.IO   │ MJPEG       │ Socket.IO     │ Socket.IO│
└───────┼─────────────┼─────────────┼───────────────┼──────────┘
        │             │             │               │
┌───────▼─────────────▼─────────────▼───────────────▼──────────┐
│                Flask + Socket.IO Backend (app.py)              │
│                                                                │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Camera      │  │ Inference    │  │ Sensor Polling       │  │
│  │ Thread      │──│ Thread       │  │ Thread               │  │
│  │ (capture)   │  │ (YOLO+Phase1)│  │ (ultrasonic/IR/line) │  │
│  └──────┬──────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         │                │                      │              │
│    FrameManager    Context Manager         Raspbot_Lib        │
│    (shared frame)  (SQLite scene DB)       (I2C hardware)     │
└────────────────────────────────────────────────────────────────┘
```

**Threading Model**: Five daemon threads run concurrently:
1. **Camera capture** — reads frames into a shared `FrameManager`
2. **Inference** — pulls frames from `FrameManager`, runs YOLO (and Phase 1 at 1Hz)
3. **Sensor polling** — reads ultrasonic/line/IR sensors at ~3Hz
4. **Status broadcast** — pushes robot state to all clients at 4Hz
5. **System monitor** — collects CPU/RAM/temp at 1Hz

## 8. Future Work / Experimental

- **C++ backend** (`backend_cpp/`): Rewrite targeting 30+ FPS YOLO inference via ONNX Runtime on CPU/GPU. Status: scaffolded, not yet functional.
- **Rust backend** (`backend_rust/`): Alternative high-performance backend using NCNN or ONNX Runtime with native camera/WebSocket integration. Status: scaffolded, not yet functional.
- **GPU acceleration**: Vulkan compute for inference on Pi 5's VideoCore VII (research in `backend/vulkan_test.py`).
- **Autonomous behaviors**: Line following, obstacle avoidance using sensor data + detection results.

## 9. Success Metrics

| Metric | Target |
|--------|--------|
| End-to-end control latency on LAN | < 100ms |
| Detection overlay FPS (with YOLO running) | >= 15 FPS |
| Context switch time (scene recognition → model reload → new detections) | < 3 seconds |
| System uptime under continuous operation | > 12 hours (validated by YouTube livestream segmentation) |
| Dashboard loads and is interactive | < 3 seconds on LAN |
