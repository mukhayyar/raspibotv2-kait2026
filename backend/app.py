#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PENS-KAIT 2026 — Robot Control Web Dashboard
Flask + Socket.IO server for real-time robot control via browser.
"""

import sys
import os
import time
import threading
import json
import uuid
import traceback
import subprocess
import sqlite3
import numpy as np
import psutil
import csv
from datetime import datetime
from flask import Flask, render_template, Response, request, jsonify, session
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
from context_manager import ContextManager
from models.phase1_model import Phase1Model

# Load environment variables from .env
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# Optional: cv2 for camera streaming
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("[WARN] opencv not available — camera feed disabled.")

# Add parent directories so we can import Raspbot_Lib
# Works locally:  backend/ → PENS-KAIT 2026/ → yahboom_control/
# Works in Docker: py_install is mounted at /app/py_install
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, _project_root)
sys.path.insert(0, os.path.join(_project_root, 'py_install', 'build', 'lib'))
# Docker mount path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'py_install', 'build', 'lib'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'py_install'))

# Try to import the robot library with a timeout (I2C init may hang without hardware)
HARDWARE_AVAILABLE = False
car = None

def _try_init_hardware():
    global car, HARDWARE_AVAILABLE
    try:
        from Raspbot_Lib.Raspbot_Lib import Raspbot
        print("[DEBUG] Raspbot_Lib imported successfully, initializing...")
        car = Raspbot()
        HARDWARE_AVAILABLE = True
        print("[DEBUG] Raspbot() init OK")
    except Exception as e:
        print(f"[DEBUG] Hardware init failed: {type(e).__name__}: {e}")

_hw_thread = threading.Thread(target=_try_init_hardware, daemon=True)
_hw_thread.start()
_hw_thread.join(timeout=3)

if HARDWARE_AVAILABLE:
    print("[OK] Raspbot hardware initialized successfully.")
else:
    print("[WARN] Raspbot hardware not available (timeout or error).")
    print("[INFO] Running in MOCK mode — commands will be logged only.")

# ─── YOLO Model ───────────────────────────────────────────────────────────────
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  HOW TO CHANGE THE MODEL                                           ║
# ║                                                                    ║
# ║  1. Place your .pt file in the  backend/models/  directory         ║
# ║  2. Change the filename below to match your model:                 ║
# ║                                                                    ║
# ║     Available models in models/ directory:                         ║
# ║       • yolov8s-worldv2.pt  (YOLOWorld — supports set_classes)     ║
# ║       • yolo26n.pt          (YOLO v11/26 nano — fast, lightweight) ║
# ║       • yolo26s.pt          (YOLO v11/26 small — more accurate)   ║
# ║                                                                    ║
# ║  3. Update DEFAULT_CLASSES if your model uses different classes    ║
# ║  4. Restart the server:  python app.py                            ║
# ╚══════════════════════════════════════════════════════════════════════╝

# ──── Model Configuration (EDIT THESE) ────────────────────────────────────────
# yolo26n.pt   — COCO-80, nano, ~8-9 FPS @ imgsz=160 on Pi 5   ← fast, current
# yolov8s-worldv2.pt — COCO-open, small, ~3 FPS @ imgsz=160    ← needed for set_classes()
_MODEL_FILENAME = 'yolov8s-worldv2.pt'
DEFAULT_CLASSES = ["person", "car", "clock", "bottle", "chair", "book", "cell phone", "scissor", "laptop", "tv", "cup", "remote", "mouse"]
# Inference image size.  Pi 5 benchmarks (WorldV2-small, CPU):
#   imgsz=320  ~320 ms  (3.1 FPS)
#   imgsz=256  ~240 ms  (4.2 FPS)
#   imgsz=192  ~180 ms  (5.6 FPS)
#   imgsz=160  ~125 ms  (8.0 FPS)  ← ~30% faster than 192, minor accuracy tradeoff
_INFER_IMGSZ = 320
# ──────────────────────────────────────────────────────────────────────────────

YOLO_AVAILABLE = False
IS_WORLD_MODEL = 'world' in _MODEL_FILENAME.lower()  # Only WorldV2 supports set_classes()
yolo_model = None
_model_path = os.path.join(os.path.dirname(__file__), 'models', _MODEL_FILENAME)

# ─── Benchmark: Base YOLO model (runs in parallel with WorldV2 for speed comparison)
_BASE_MODEL_FILENAME = 'yolov8s.pt'
_yolo_base_model = None   # loaded at startup; base_inference_thread runs it concurrently

try:
    from ultralytics import YOLO
    if os.path.exists(_model_path):
        yolo_model = YOLO(_model_path)
        if IS_WORLD_MODEL:
            yolo_model.set_classes(DEFAULT_CLASSES)
            print(f"[OK] YOLOWorld model loaded — dynamic class changes supported")
        else:
            print(f"[OK] YOLO model loaded — using model's built-in classes")
        YOLO_AVAILABLE = True
        print(f"[OK] Model path: {_model_path}")
    else:
        print(f"[WARN] YOLO model file not found: {_model_path}")
except ImportError:
    print("[WARN] ultralytics not installed — YOLO detection disabled.")
except Exception as e:
    print(f"[WARN] YOLO init error: {e}")

if YOLO_AVAILABLE:
    print(f"[DEBUG] YOLO is available. Model type: {type(yolo_model).__name__}")
else:
    print("[DEBUG] YOLO is NOT available.")

# Load base YOLOv8s model — prefer ONNX (faster on ARM CPU via OnnxRuntime)
_base_model_path = os.path.join(os.path.dirname(__file__), 'models', _BASE_MODEL_FILENAME)
_base_onnx_path  = _base_model_path.replace('.pt', '.onnx')

def _load_base_model():
    """Load base model (.pt only — ONNX static shapes conflict with dynamic imgsz)."""
    global _yolo_base_model
    if not YOLO_AVAILABLE:
        return
    if os.path.exists(_base_model_path):
        try:
            _yolo_base_model = YOLO(_base_model_path)
            print(f"[OK] YOLOv8s base model loaded (.pt): {_BASE_MODEL_FILENAME}")
        except Exception as e:
            print(f"[WARN] YOLOv8s base model load error: {e}")
    else:
        print(f"[INFO] YOLOv8s base model not found: {_base_model_path}")

_load_base_model()

# ─── Phase 1 Model ──────────────────────────────────────────────────────────
phase1_model = None
try:
    phase1_model = Phase1Model(os.path.dirname(os.path.abspath(__file__)))
    print("[OK] Phase 1 (Places365) initialized.")
except Exception as e:
    print(f"[WARN] Phase 1 init failed: {e}")


# Detection state
detection_lock = threading.Lock()

# Serialises yolo_model.predict() vs yolo_model.set_classes() calls.
# set_classes() mutates the WorldV2 detection head; a concurrent predict()
# will see inconsistent tensor sizes and raise a reshape error.
_infer_lock = threading.Lock()
detection_state = {
    "enabled": False,
    "confidence": 0.25,
    "classes": DEFAULT_CLASSES[:],
    "detections": [],  # current frame results
}

# ─── Context Manager ──────────────────────────────────────────────────────────
context_mgr = ContextManager()

# ─── Phase 1→2 Bridge State ─────────────────────────────────────────────────
# Tracks consecutive scene predictions to avoid thrashing on noisy classifications.
_scene_lock = threading.Lock()
_current_scene = None        # last scene that was actually applied
_candidate_scene = None      # scene being evaluated for stability
_candidate_count = 0         # how many consecutive times _candidate_scene was the top prediction
_SCENE_STABILITY_THRESHOLD = 3  # require N consecutive same-scene predictions before switching

# ─── Phase 2 Mode ────────────────────────────────────────────────────────────
# 'classes' — use yolo_classes from DB (set_classes on WorldV2, default)
# 'model'   — swap the entire YOLO model file from DB (model_file column)
_phase2_mode = 'classes'   # toggled via set_phase2_mode socket event
_context_vocab = 'coco80'  # 'coco80' or 'objects365' — toggled via set_context_vocab socket event

# ─── Detection Alert Rules ───────────────────────────────────────────────────
# User-configured rules: "when class X detected >= N times, trigger LED/buzzer action"
alert_lock = threading.Lock()
alert_rules = []              # list of rule dicts synced from frontend
alert_active = {}             # rule_id -> frame count that rule has been continuously met
alert_cooldown = {}           # rule_id -> frame count that rule has been continuously NOT met
_ALERT_TRIGGER_FRAMES = 2    # consecutive frames before triggering
_ALERT_CLEAR_FRAMES = 3      # consecutive frames absent before clearing
_buzzer_pattern_stops = {}    # rule_id -> threading.Event to stop pattern threads

def _execute_alert_action(rule, activate=True):
    """Execute or undo an alert rule's hardware action."""
    action = rule.get('action_type', '')
    params = rule.get('action_params', {})
    rule_id = rule.get('id', '')

    if action == 'led_color':
        if HARDWARE_AVAILABLE:
            if activate:
                car.Ctrl_WQ2812_ALL(1, int(params.get('color', 0)))
            else:
                car.Ctrl_WQ2812_ALL(0, 0)
        with state_lock:
            if activate:
                robot_state["led_state"] = "on"
                robot_state["led_color"] = int(params.get('color', 0))
            else:
                robot_state["led_state"] = "off"

    elif action == 'led_rgb':
        r, g, b = int(params.get('r', 0)), int(params.get('g', 0)), int(params.get('b', 0))
        if HARDWARE_AVAILABLE:
            if activate:
                car.Ctrl_WQ2812_brightness_ALL(r, g, b)
            else:
                car.Ctrl_WQ2812_brightness_ALL(0, 0, 0)
        with state_lock:
            robot_state["led_state"] = f"rgb({r},{g},{b})" if activate else "off"

    elif action == 'buzzer_on':
        if HARDWARE_AVAILABLE:
            car.Ctrl_BEEP_Switch(1 if activate else 0)
        with state_lock:
            robot_state["buzzer"] = activate

    elif action == 'buzzer_pattern':
        # Stop any existing pattern thread for this rule
        if rule_id in _buzzer_pattern_stops:
            _buzzer_pattern_stops[rule_id].set()
            del _buzzer_pattern_stops[rule_id]
        if activate:
            on_ms = int(params.get('on_ms', 200))
            off_ms = int(params.get('off_ms', 200))
            repeats = int(params.get('repeats', 3))
            stop_event = threading.Event()
            _buzzer_pattern_stops[rule_id] = stop_event

            def _pattern():
                for _ in range(repeats):
                    if stop_event.is_set():
                        break
                    if HARDWARE_AVAILABLE:
                        car.Ctrl_BEEP_Switch(1)
                    stop_event.wait(on_ms / 1000.0)
                    if stop_event.is_set():
                        break
                    if HARDWARE_AVAILABLE:
                        car.Ctrl_BEEP_Switch(0)
                    stop_event.wait(off_ms / 1000.0)
                if HARDWARE_AVAILABLE:
                    car.Ctrl_BEEP_Switch(0)
                with state_lock:
                    robot_state["buzzer"] = False
                _buzzer_pattern_stops.pop(rule_id, None)

            threading.Thread(target=_pattern, daemon=True).start()
        else:
            if HARDWARE_AVAILABLE:
                car.Ctrl_BEEP_Switch(0)
            with state_lock:
                robot_state["buzzer"] = False


def _evaluate_alert_rules(detections):
    """Check all alert rules against current detections. Called from inference thread."""
    # Build class counts
    counts = {}
    for d in detections:
        cls = d.get('class', '')
        counts[cls] = counts.get(cls, 0) + 1

    # Copy rules under lock
    with alert_lock:
        rules_snapshot = [r.copy() for r in alert_rules if r.get('enabled', True)]

    for rule in rules_snapshot:
        rule_id = rule.get('id', '')
        if not rule_id:
            continue
        cls = rule.get('class_name', '')
        threshold = rule.get('count_threshold', 1)
        detected_count = counts.get(cls, 0)
        condition_met = detected_count >= threshold

        with alert_lock:
            if condition_met:
                # Increment trigger counter, reset cooldown
                alert_cooldown.pop(rule_id, None)
                prev = alert_active.get(rule_id, 0)
                alert_active[rule_id] = prev + 1
                frame_count = alert_active[rule_id]
            else:
                # Increment cooldown counter
                if rule_id in alert_active:
                    cd = alert_cooldown.get(rule_id, 0) + 1
                    alert_cooldown[rule_id] = cd
                    frame_count = -cd  # negative means clearing
                else:
                    frame_count = 0  # never triggered, nothing to do

        # Rising edge: trigger after N consecutive frames
        if frame_count == _ALERT_TRIGGER_FRAMES:
            _execute_alert_action(rule, activate=True)
            socketio.emit('alert_triggered', {
                'rule_id': rule_id,
                'class_name': cls,
                'count': detected_count,
                'action_type': rule.get('action_type', ''),
            })
            print(f"[Alert] TRIGGERED: {cls} x{detected_count} → {rule.get('action_type')}")

        # Falling edge: clear after N consecutive absent frames
        elif frame_count == -_ALERT_CLEAR_FRAMES:
            _execute_alert_action(rule, activate=False)
            with alert_lock:
                alert_active.pop(rule_id, None)
                alert_cooldown.pop(rule_id, None)
            socketio.emit('alert_clear', {'rule_id': rule_id})
            print(f"[Alert] CLEARED: {cls} → {rule.get('action_type')}")

# ─── Phase 2: Context Switch Logic ───────────────────────────────────────────
def _switch_scene(scene_name):
    """
    Perform the Phase 2 context switch: look up the scene in the DB,
    then act according to _phase2_mode:
      'classes' — call set_classes() on the current WorldV2 model
      'model'   — hot-swap the YOLO model file from the DB (ignores classes column)
    Safe to call from any thread (uses socketio.emit for broadcast).
    """
    global yolo_model, _MODEL_FILENAME, IS_WORLD_MODEL, YOLO_AVAILABLE, _phase2_mode, _context_vocab

    if not scene_name:
        return

    print(f"[Phase2] Switching context to scene: {scene_name} (mode={_phase2_mode}, vocab={_context_vocab})")

    # ── Idempotency key — one UUID per logical switch event ───────────────────
    switch_id = str(uuid.uuid4())

    # ── Timing accumulators ────────────────────────────────────────────────────
    t_total_start = time.perf_counter()
    t_db_ms = 0.0
    t_switch_ms = 0.0   # set_classes() or model load time

    # 1. Query Database for context
    _t0 = time.perf_counter()
    ctx = context_mgr.get_context_for_scene(scene_name, vocabulary=_context_vocab)
    t_db_ms = (time.perf_counter() - _t0) * 1000

    target_classes = ctx['classes']
    target_model_file = ctx['model']

    print(f"[Phase2] DB query: {t_db_ms:.1f} ms  →  '{scene_name}': {len(target_classes)} classes, model={target_model_file}")

    if _phase2_mode == 'model':
        # ── Model-swap mode: load the model file from DB, ignore classes ──
        if not target_model_file or target_model_file == _MODEL_FILENAME:
            print(f"[Phase2][model] No model change needed ({_MODEL_FILENAME})")
        else:
            new_model_path = os.path.join(os.path.dirname(__file__), 'models', target_model_file)
            if os.path.exists(new_model_path):
                try:
                    print(f"[Phase2][model] Loading model: {target_model_file}...")
                    from ultralytics import YOLO as _YOLO
                    _t0 = time.perf_counter()
                    new_model = _YOLO(new_model_path)
                    t_switch_ms = (time.perf_counter() - _t0) * 1000
                    with detection_lock:
                        yolo_model = new_model
                        _MODEL_FILENAME = target_model_file
                        IS_WORLD_MODEL = 'world' in _MODEL_FILENAME.lower()
                        YOLO_AVAILABLE = True
                    print(f"[Phase2][model] Model loaded in {t_switch_ms:.1f} ms  →  {_MODEL_FILENAME}")
                except Exception as e:
                    print(f"[ERROR] Failed to load model {target_model_file}: {e}")
                    socketio.emit('model_update_error', {'error': str(e)})
                    return
            else:
                print(f"[WARN] Model file {target_model_file} not found, keeping {_MODEL_FILENAME}")

        if not YOLO_AVAILABLE:
            return

        # Report current model's known classes (or empty list for fixed models)
        active_classes = target_classes if IS_WORLD_MODEL else []
        with detection_lock:
            detection_state["enabled"] = True

        t_total_ms = (time.perf_counter() - t_total_start) * 1000
        print(f"[Phase2][model] Total switch: {t_total_ms:.1f} ms  (db={t_db_ms:.1f} ms, load={t_switch_ms:.1f} ms)")
        _log_inference_switch(switch_id, scene_name, "model", len(active_classes),
                              round(t_db_ms, 2), round(t_switch_ms, 2), round(t_total_ms, 2),
                              model_file=_MODEL_FILENAME)
        socketio.emit('phase2_timing', {
            "switch_id": switch_id,
            "scene": scene_name, "mode": "model",
            "num_classes": len(active_classes),
            "db_query_ms": round(t_db_ms, 2),
            "switch_ms": round(t_switch_ms, 2),
            "total_ms": round(t_total_ms, 2),
        })
        socketio.emit('detection_state', {
            "enabled": True,
            "confidence": detection_state["confidence"],
            "classes": active_classes,
            "yolo_available": YOLO_AVAILABLE,
            "detections": detection_state["detections"],
        })
        socketio.emit('context_switched', {
            "scene": scene_name,
            "classes": active_classes,
            "model": _MODEL_FILENAME,
            "mode": "model",
        })

    else:
        # ── Classes mode (default): set_classes() on WorldV2, no model swap ──
        if not YOLO_AVAILABLE:
            return

        try:
            if IS_WORLD_MODEL:
                _t0 = time.perf_counter()
                with _infer_lock:   # block until any in-flight predict() finishes
                    yolo_model.set_classes(target_classes)
                t_switch_ms = (time.perf_counter() - _t0) * 1000
                print(f"[Phase2][classes] set_classes({len(target_classes)} classes) in {t_switch_ms:.1f} ms  →  {target_classes[:4]}…")
            else:
                print(f"[Phase2][classes] {_MODEL_FILENAME} is fixed-class; skipping set_classes.")

            with detection_lock:
                detection_state["classes"] = target_classes
                detection_state["enabled"] = True

            t_total_ms = (time.perf_counter() - t_total_start) * 1000
            print(f"[Phase2][classes] Total switch: {t_total_ms:.1f} ms  (db={t_db_ms:.1f} ms, set_classes={t_switch_ms:.1f} ms)")
            _log_inference_switch(switch_id, scene_name, "classes", len(target_classes),
                                  round(t_db_ms, 2), round(t_switch_ms, 2), round(t_total_ms, 2),
                                  model_file=_MODEL_FILENAME)
            socketio.emit('phase2_timing', {
                "switch_id": switch_id,
                "scene": scene_name, "mode": "classes",
                "num_classes": len(target_classes),
                "db_query_ms": round(t_db_ms, 2),
                "switch_ms": round(t_switch_ms, 2),
                "total_ms": round(t_total_ms, 2),
            })
            socketio.emit('detection_class_update', {"success": True, "classes": target_classes})
            socketio.emit('detection_state', {
                "enabled": True,
                "confidence": detection_state["confidence"],
                "classes": target_classes,
                "yolo_available": YOLO_AVAILABLE,
                "detections": detection_state["detections"],
            })
            socketio.emit('context_switched', {
                "scene": scene_name,
                "classes": target_classes,
                "model": _MODEL_FILENAME,
                "mode": "classes",
            })
        except Exception as e:
            print(f"[ERROR] Context switch (classes mode) failed: {e}")


# ─── Authentication ───────────────────────────────────────────────────────────
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin')
authenticated_sessions = set()  # set of session IDs that have authenticated
auth_lock = threading.Lock()

def _require_auth():
    """Check if the current Socket.IO session is authenticated.
    Returns True if authenticated, else emits an error and returns False."""
    sid = request.sid
    with auth_lock:
        if sid in authenticated_sessions:
            return True
    emit('auth_state', {'authenticated': False, 'message': 'Please unlock to control the robot.'})
    return False

# ─── SQLite Access Logging ────────────────────────────────────────────────────
_db_dir = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(_db_dir, exist_ok=True)
_db_path = os.path.join(_db_dir, 'access.db')
_db_lock = threading.Lock()

def _init_db():
    """Create access_log and inference_history tables if they don't exist."""
    with sqlite3.connect(_db_path) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS access_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                event TEXT NOT NULL,
                client_ip TEXT,
                session_id TEXT,
                details TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS inference_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                switch_id   TEXT UNIQUE NOT NULL,
                ts          TEXT NOT NULL,
                scene       TEXT NOT NULL,
                mode        TEXT NOT NULL,
                num_classes INTEGER NOT NULL DEFAULT 0,
                db_query_ms REAL    NOT NULL DEFAULT 0,
                switch_ms   REAL    NOT NULL DEFAULT 0,
                total_ms    REAL    NOT NULL DEFAULT 0,
                model_file  TEXT
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_infer_ts ON inference_history(ts)')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS phase1_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                infer_id    TEXT UNIQUE NOT NULL,
                ts          TEXT NOT NULL,
                scene       TEXT NOT NULL,
                confidence  REAL NOT NULL DEFAULT 0,
                inference_ms REAL NOT NULL DEFAULT 0
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_p1_ts ON phase1_history(ts)')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS yolo_comparison_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ts              TEXT    NOT NULL,
                model_key       TEXT    NOT NULL,
                model_name      TEXT    NOT NULL,
                scene           TEXT,
                preprocess_ms   REAL    NOT NULL DEFAULT 0,
                inference_ms    REAL    NOT NULL DEFAULT 0,
                postprocess_ms  REAL    NOT NULL DEFAULT 0,
                total_ms        REAL    NOT NULL DEFAULT 0,
                imgsz           INTEGER NOT NULL DEFAULT 0,
                detection_count INTEGER NOT NULL DEFAULT 0,
                avg_conf        REAL    NOT NULL DEFAULT 0,
                detections      TEXT    NOT NULL DEFAULT '[]'
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_yolo_log_ts       ON yolo_comparison_log(ts)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_yolo_log_model_key ON yolo_comparison_log(model_key)')
        # Migration: add detections column to existing tables that predate this field
        try:
            conn.execute("ALTER TABLE yolo_comparison_log ADD COLUMN detections TEXT NOT NULL DEFAULT '[]'")
        except Exception:
            pass  # column already exists
        conn.commit()
    print(f"[OK] Access log database: {_db_path}")


def _log_inference_switch(switch_id, scene, mode, num_classes,
                           db_query_ms, switch_ms, total_ms, model_file=None):
    """
    Persist a Phase 2 scene-switch record.
    INSERT OR IGNORE on switch_id guarantees idempotency — duplicate calls
    (e.g. retry, double-trigger) are silently discarded.
    """
    try:
        with _db_lock:
            with sqlite3.connect(_db_path) as conn:
                conn.execute(
                    '''INSERT OR IGNORE INTO inference_history
                       (switch_id, ts, scene, mode, num_classes,
                        db_query_ms, switch_ms, total_ms, model_file)
                       VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                               ?, ?, ?, ?, ?, ?, ?)''',
                    (switch_id, scene, mode, num_classes,
                     db_query_ms, switch_ms, total_ms, model_file)
                )
                conn.commit()
    except Exception as e:
        print(f"[WARN] Failed to log inference switch: {e}")

def _log_phase1_inference(infer_id, scene, confidence, inference_ms):
    """Persist a Phase 1 scene prediction. INSERT OR IGNORE for idempotency."""
    try:
        with _db_lock:
            with sqlite3.connect(_db_path) as conn:
                conn.execute(
                    '''INSERT OR IGNORE INTO phase1_history
                       (infer_id, ts, scene, confidence, inference_ms)
                       VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ','now'), ?, ?, ?)''',
                    (infer_id, scene, confidence, inference_ms)
                )
                conn.commit()
    except Exception as e:
        print(f"[WARN] Failed to log phase1 inference: {e}")

# ─── YOLO Comparison Logger ──────────────────────────────────────────────────
# Throttled to 1 DB row per model per second so the table doesn't grow
# unboundedly during long research sessions.  Writes are dispatched to a
# tiny background thread so the inference loop is never blocked by I/O.
_yolo_log_last = {'worldv2': 0.0, 'base': 0.0}
_yolo_log_interval = 1.0   # seconds between logged samples per model

def _log_yolo_infer(model_key, model_name, scene,
                    preprocess_ms, inference_ms, postprocess_ms, total_ms,
                    imgsz, detection_count, avg_conf, detections=None):
    """Write one row to yolo_comparison_log (throttled, non-blocking).
    detections: list of class-name strings, e.g. ['person','car','person']
    """
    import json as _json
    now = time.time()
    if now - _yolo_log_last.get(model_key, 0.0) < _yolo_log_interval:
        return
    _yolo_log_last[model_key] = now
    det_json = _json.dumps(detections or [])

    def _write():
        try:
            with _db_lock:
                with sqlite3.connect(_db_path) as conn:
                    conn.execute(
                        '''INSERT INTO yolo_comparison_log
                           (ts, model_key, model_name, scene,
                            preprocess_ms, inference_ms, postprocess_ms, total_ms,
                            imgsz, detection_count, avg_conf, detections)
                           VALUES (strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                                   ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        (model_key, model_name, scene,
                         preprocess_ms, inference_ms, postprocess_ms, total_ms,
                         imgsz, detection_count, avg_conf, det_json)
                    )
                    conn.commit()
        except Exception as e:
            print(f"[WARN] yolo_comparison_log write failed: {e}")

    threading.Thread(target=_write, daemon=True).start()

def _log_access(event, details="", sid=None, ip=None):
    """Log an access event to the SQLite database."""
    try:
        if sid is None:
            try: sid = request.sid
            except: sid = 'unknown'
        if ip is None:
            try: ip = request.remote_addr or request.environ.get('HTTP_X_FORWARDED_FOR', 'unknown')
            except: ip = 'unknown'
        with _db_lock:
            with sqlite3.connect(_db_path) as conn:
                conn.execute(
                    'INSERT INTO access_log (event, client_ip, session_id, details) VALUES (?, ?, ?, ?)',
                    (event, ip, sid[:16] if sid else '', details)
                )
                conn.commit()
    except Exception as e:
        print(f"[WARN] Failed to log access: {e}")

_init_db()

# ─── Flask + SocketIO ─────────────────────────────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY'] = 'pens-kait-2026'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ─── Robot State ──────────────────────────────────────────────────────────────
state_lock = threading.Lock()
robot_state = {
    "speed": 40,
    "w_angle": 40,
    "h_angle": 40,
    "motors": {
        "L1": {"id": 0, "dir": 0, "speed": 0},
        "L2": {"id": 1, "dir": 0, "speed": 0},
        "R1": {"id": 2, "dir": 0, "speed": 0},
        "R2": {"id": 3, "dir": 0, "speed": 0},
    },
    "led_state": "off",
    "led_color": 0,
    "buzzer": False,
    "ultrasonic_mm": None,
    "line_track": {"x1": 0, "x2": 0, "x3": 0, "x4": 0},
    "ir_value": None,
    "direction": "stopped",
    "connected": True,
}

# ─── Global State & Shared Frames ─────────────────────────────────────────────
research_active = False

class FrameManager:
    def __init__(self):
        self.raw_frame = None
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)  # efficient wait-for-new-frame
        self.last_update_time = 0
        self.frame_id = 0  # increments every new camera frame

    def update(self, frame):
        with self.condition:
            self.raw_frame = frame
            self.last_update_time = time.time()
            self.frame_id += 1
            self.condition.notify_all()  # wake all waiting threads instantly

    def get(self):
        with self.lock:
            return self.raw_frame.copy() if self.raw_frame is not None else None

    def get_with_id(self):
        """Return (frame_copy, frame_id) atomically for deduplication."""
        with self.lock:
            if self.raw_frame is None:
                return None, -1
            return self.raw_frame.copy(), self.frame_id

    def wait_for_new(self, last_id: int, timeout: float = 1.0) -> tuple:
        """Block until a frame newer than last_id arrives, then return (copy, new_id).
        Returns (None, last_id) on timeout. Zero polling — uses OS condition variable."""
        with self.condition:
            self.condition.wait_for(
                lambda: self.frame_id != last_id or self.raw_frame is None,
                timeout=timeout
            )
            if self.raw_frame is None:
                return None, last_id
            return self.raw_frame.copy(), self.frame_id

    def is_stale(self, timeout: float = 10.0) -> bool:
        """Return True if no frame has been written for longer than `timeout` seconds."""
        with self.lock:
            if self.last_update_time == 0:
                return False  # not started yet — not "stale"
            return (time.time() - self.last_update_time) > timeout

frame_manager = FrameManager()

# ─── Pre-encoded MJPEG cache ──────────────────────────────────────────────────
# One encoder thread produces ready-to-stream JPEG bytes; HTTP generators just
# read from this cache — eliminates N×encoding when N clients are connected.
# _jpeg_cache_cond is notified every time the encoder writes new frames so that
# HTTP streamers wake immediately (event-driven, no polling drift or duplicates).
_jpeg_cache_lock    = threading.Lock()
_jpeg_cache_cond    = threading.Condition(_jpeg_cache_lock)
_jpeg_cache_version = 0  # incremented each encoder cycle; streamers track last-seen
_jpeg_raw           = None  # bytes: latest raw frame with P1 overlay
_jpeg_annotated     = None  # bytes: latest annotated frame with WorldV2 detections
_jpeg_base          = None  # bytes: latest annotated frame with YOLOv8s base detections

# Base model detection results (separate from WorldV2's detection_state)
_base_detection_lock   = threading.Lock()
_base_detection_results = []  # list of {bbox, class, id, conf}

# ─── WebRTC via aiortc ────────────────────────────────────────────────────────
# Runs in a dedicated asyncio loop thread, fully isolated from eventlet greenlets.
WEBRTC_AVAILABLE = False
_webrtc_loop = None
_webrtc_pcs  = set()   # active RTCPeerConnection objects (for lifecycle tracking)

try:
    import asyncio as _aio
    import av as _av
    from aiortc import RTCPeerConnection, RTCSessionDescription
    from aiortc.mediastreams import VideoStreamTrack as _AiortcVideoTrack
    WEBRTC_AVAILABLE = True
    print("[OK] aiortc available — WebRTC enabled.")
except ImportError:
    print("[WARN] aiortc not installed — WebRTC disabled.  pip install aiortc")

if WEBRTC_AVAILABLE:
    import threading as _thr

    def _capture_frame_sync(mode):
        """Sync frame capture + BGR→RGB conversion. Run via executor to avoid
        blocking the aiortc asyncio event loop (frame_manager.get() acquires a
        threading.Lock and cv2.cvtColor is CPU-bound)."""
        frame_bgr = frame_manager.get()   # returns a copy; safe to mutate
        if frame_bgr is None:
            frame_bgr = np.zeros((480, 640, 3), dtype=np.uint8)
        if mode == "annotated":
            with detection_lock:
                results = list(detection_state.get("last_results", []))
            if results:
                _draw_results(frame_bgr, results)
        return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

    class CameraVideoTrack(_AiortcVideoTrack):
        """
        aiortc VideoStreamTrack that pulls the latest BGR frame from FrameManager,
        optionally applies YOLO bounding-box overlays, converts to RGB, and
        delivers it to the WebRTC peer connection.

        Frame acquisition and colour conversion are offloaded to a thread-pool
        executor so the aiortc asyncio event loop is never blocked by lock
        contention or CPU-bound work.
        """
        kind = "video"

        def __init__(self, mode="raw"):
            super().__init__()
            self.mode = mode   # "raw" | "annotated"

        async def recv(self):
            pts, time_base = await self.next_timestamp()
            loop = _aio.get_event_loop()
            # Run blocking frame work in the default thread-pool executor so the
            # event loop stays responsive for ICE keepalives and DTLS retransmits.
            frame_rgb = await loop.run_in_executor(
                None, _capture_frame_sync, self.mode
            )
            vf = _av.VideoFrame.from_ndarray(frame_rgb, format="rgb24")
            vf.pts, vf.time_base = pts, time_base
            return vf

    async def _handle_webrtc_offer(sdp, offer_type, mode):
        pc = RTCPeerConnection()
        _webrtc_pcs.add(pc)

        @pc.on("connectionstatechange")
        async def on_state():
            state = pc.connectionState
            print(f"[WebRTC] Peer state → {state}")
            if state in ("failed", "closed", "disconnected"):
                await pc.close()
                _webrtc_pcs.discard(pc)

        pc.addTrack(CameraVideoTrack(mode))
        await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type=offer_type))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        # Wait for full ICE gathering so we can send a single complete SDP answer
        # (avoids trickle-ICE complexity; fine for LAN with a 5-second budget)
        if pc.iceGatheringState != "complete":
            gathered = _aio.Event()

            @pc.on("icegatheringstatechange")
            def _on_ice():
                if pc.iceGatheringState == "complete":
                    gathered.set()

            try:
                await _aio.wait_for(gathered.wait(), timeout=5.0)
            except _aio.TimeoutError:
                print("[WebRTC] ICE gathering timed out — sending partial candidates")

        return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}

    def _start_webrtc_loop():
        global _webrtc_loop
        _webrtc_loop = _aio.new_event_loop()
        _aio.set_event_loop(_webrtc_loop)
        print("[WebRTC] asyncio event loop started.")
        _webrtc_loop.run_forever()

    _thr.Thread(target=_start_webrtc_loop, daemon=True, name="aiortc-loop").start()

# ─── Camera Thread (Capture Only) ─────────────────────────────────────────────
class LibCameraCapture:
    """Wrapper to use rpicam-vid/libcamera-vid via subprocess for Pi 5 CSI cameras."""
    def __init__(self, width=640, height=640, framerate=15):
        self.width = width
        self.height = height
        self.frame_size = int(width * height * 1.5) # YUV420 size
        self.proc = None
        for cmd in ['rpicam-vid', 'libcamera-vid']:
            try:
                self.proc = subprocess.Popen(
                    [cmd, '-t', '0', '--nopreview', '--width', str(width),
                     '--height', str(height), '--framerate', str(framerate),
                     '--codec', 'yuv420', '--vflip', '--hflip', '-o', '-'],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    bufsize=int(width * height * 1.5 * 4),  # 4-frame buffer — absorbs GIL pauses
                )
                break
            except FileNotFoundError:
                continue

    def isOpened(self):
        return self.proc is not None and self.proc.poll() is None

    def read(self):
        if not self.isOpened():
            return False, None
        raw = self.proc.stdout.read(self.frame_size)
        if len(raw) != self.frame_size:
            return False, None
        yuv = np.frombuffer(raw, dtype=np.uint8).reshape((self.height + self.height // 2, self.width))
        bgr = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_I420)
        return True, bgr

    def set(self, prop, value):
        pass # Not applicable for this simple wrapper
        
    def release(self):
        if self.proc:
            self.proc.terminate()
            self.proc.wait()

def camera_capture_thread():
    """Reads frames from the camera as fast as possible."""
    global CV2_AVAILABLE
    if not CV2_AVAILABLE:
        print("[WARN] Camera thread exiting: OpenCV not available.")
        return

    # Check for requested camera type (CSI or USB). Default to auto-detect.
    camera_type = os.environ.get('CAMERA_TYPE', 'AUTO').upper()
    cap = None

    if camera_type in ['CSI', 'AUTO']:
        print("[INFO] Attempting to open CSI Camera via libcamera subprocess...")
        cap = LibCameraCapture()
        if cap.isOpened():
            print("[OK] CSI Camera opened successfully (libcamera).")
        else:
            if camera_type == 'CSI':
                print("[ERR] Requested CSI Camera but failed to open.")
            cap = None

    if (cap is None or not cap.isOpened()) and camera_type in ['USB', 'AUTO']:
        print("[INFO] Attempting to open USB Camera (default index 0)...")
        cap = cv2.VideoCapture(0)
        if cap is not None and cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 15)  # limit USB camera to 15 FPS
            print("[OK] USB Camera opened successfully (index 0).")
        else:
            if camera_type == 'USB':
                print("[ERR] Requested USB Camera but failed to open.")
            cap = None

    if cap is None or not cap.isOpened():
        print("[ERR] Could not open any camera. Verify connections and permissions.")
        return

    print("[OK] Camera capture thread running.")

    fps = 0.0
    fps_start_time = time.time()
    fps_frames = 0
    consecutive_failures = 0
    _MAX_FAILURES = 30   # after this many consecutive bad reads, restart the capture device
    _CAM_INTERVAL = 1.0 / 15  # hard cap: never push more than 15 FPS to inference threads
    _last_cam_time = time.monotonic()

    while True:
        try:
            ok, frame = cap.read()
            if not ok:
                consecutive_failures += 1
                if consecutive_failures >= _MAX_FAILURES:
                    print(f"[WARN] Camera: {consecutive_failures} consecutive read failures — attempting restart...")
                    try:
                        cap.release()
                    except Exception:
                        pass
                    time.sleep(2)
                    # Re-open using the same priority logic as startup
                    cap = None
                    if camera_type in ['CSI', 'AUTO']:
                        cap = LibCameraCapture()
                        if not cap.isOpened():
                            cap = None
                    if cap is None and camera_type in ['USB', 'AUTO']:
                        cap = cv2.VideoCapture(0)
                        if cap.isOpened():
                            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        else:
                            cap = None
                    if cap is None:
                        print("[ERR] Camera restart failed — retrying in 5 s...")
                        time.sleep(5)
                    else:
                        print("[OK] Camera restarted successfully.")
                        consecutive_failures = 0
                else:
                    time.sleep(0.1)
                continue

            consecutive_failures = 0

            # FPS calculation
            fps_frames += 1
            now = time.time()
            if now - fps_start_time >= 1.0:
                fps = fps_frames / (now - fps_start_time)
                fps_frames = 0
                fps_start_time = now
                with state_lock:
                    robot_state['fps'] = fps

            # Hard-cap frame rate.  time.sleep() alone overshoots by 5–15 ms on
            # Linux for small durations (kernel timer resolution), which creates
            # alternating fast/slow frame gaps and visible jitter in the browser.
            # Fix: sleep for most of the interval, then spin-wait for the remainder.
            _deadline = _last_cam_time + _CAM_INTERVAL
            _remaining = _deadline - time.monotonic()
            if _remaining > 0.002:               # > 2 ms: coarse sleep
                time.sleep(_remaining - 0.001)   # leave 1 ms margin
            while time.monotonic() < _deadline:  # spin for the last ~1 ms
                pass
            _last_cam_time = time.monotonic()

            # Draw FPS overlay directly on the capture frame
            cv2.putText(frame, f"Cam FPS: {fps:.1f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            frame_manager.update(frame)
        except Exception as e:
            print(f"[ERR] Camera capture loop: {e}")
            time.sleep(1)

# ─── Phase 1 Thread (Places365 scene recognition) ─────────────────────────────
def phase1_thread():
    """
    Runs GoogLeNet Places365 inference at ~1 Hz in its own thread.
    Completely decoupled from YOLO so it never blocks detection.
    """
    global _candidate_scene, _candidate_count, _current_scene
    print("[OK] Phase 1 thread started.")
    _P1_INTERVAL = 1.0  # seconds between scene predictions

    while True:
        try:
            if phase1_model is None:
                time.sleep(1)
                continue

            index_enabled = detection_state["enabled"]
            if not (index_enabled or research_active):
                time.sleep(0.5)
                continue

            frame = frame_manager.get()
            if frame is None:
                time.sleep(0.2)
                continue

            _t0 = time.perf_counter()
            p1_results = phase1_model.predict(frame)
            p1_ms = (time.perf_counter() - _t0) * 1000

            with state_lock:
                robot_state['phase1_ms'] = round(p1_ms, 1)

            socketio.emit('phase1_result', p1_results)

            # ── Emit Phase 1 timing + persist to DB ───────────────────────────
            if p1_results:
                top = p1_results[0]
                top_label = top.get('label', '').split('/')[-1].strip()
                top_conf  = round(float(top.get('score', 0.0)), 4)
                infer_id  = str(uuid.uuid4())
                socketio.emit('phase1_timing', {
                    'infer_id':    infer_id,
                    'scene':       top_label,
                    'confidence':  top_conf,
                    'inference_ms': round(p1_ms, 1),
                })
                threading.Thread(
                    target=_log_phase1_inference,
                    args=(infer_id, top_label, top_conf, round(p1_ms, 1)),
                    daemon=True,
                ).start()

            if p1_results:
                top_scene = p1_results[0].get('label', '').split('/')[-1].strip()
                if top_scene:
                    with _scene_lock:
                        if top_scene == _candidate_scene:
                            _candidate_count += 1
                        else:
                            _candidate_scene = top_scene
                            _candidate_count = 1

                        if _candidate_count >= _SCENE_STABILITY_THRESHOLD and top_scene != _current_scene:
                            print(f"[Phase1→2] Scene stable: '{top_scene}' ({_candidate_count}×). Triggering switch.")
                            _current_scene = top_scene
                            _candidate_count = 0
                            threading.Thread(target=_switch_scene, args=(top_scene,), daemon=True).start()

            # Sleep the remainder of the interval minus inference time
            elapsed = (time.perf_counter() - _t0)
            time.sleep(max(0.0, _P1_INTERVAL - elapsed))

        except Exception as e:
            print(f"[ERR] Phase 1 thread: {e}")
            time.sleep(1)


# ─── MJPEG Encoder Thread ─────────────────────────────────────────────────────
def mjpeg_encoder_thread():
    """
    Single thread that pre-encodes BOTH frame variants at up to 30 FPS.
    All HTTP streaming endpoints read from the cache — zero redundant encoding
    regardless of how many browser clients are connected.
    """
    global _jpeg_raw, _jpeg_annotated, _jpeg_base, _jpeg_cache_version
    last_frame_id = -1
    _MJPEG_QUALITY = 55  # lower quality = faster encode, less CPU

    print("[OK] MJPEG encoder thread started.")
    while True:
        try:
            frame, frame_id = frame_manager.wait_for_new(last_frame_id, timeout=1.0)
            if frame is None or frame_id == last_frame_id:
                continue
            last_frame_id = frame_id

            # Snapshot shared state once, outside any heavy locks
            with detection_lock:
                results = list(detection_state.get("last_results", []))
            with _base_detection_lock:
                base_results = list(_base_detection_results)
            with state_lock:
                infer_fps = robot_state.get('infer_fps', 0.0)
                phase1_ms = robot_state.get('phase1_ms', 0.0)

            # All three variants are drawn from the same camera frame — no second
            # frame_manager.get() call, so all feeds stay in sync with each other.
            ann_frame  = frame            # already a copy from wait_for_new
            raw_frame  = frame.copy()
            base_frame = frame.copy()

            # ── Annotated variant (WorldV2 detection boxes) ───────────────────
            if results:
                _draw_results(ann_frame, results)
            cv2.putText(ann_frame, f"Infer FPS: {infer_fps:.1f}", (10, 55),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
            ok_ann, jpeg_ann = cv2.imencode('.jpg', ann_frame,
                                            [cv2.IMWRITE_JPEG_QUALITY, _MJPEG_QUALITY])

            # ── Raw variant (P1 overlay only) ─────────────────────────────────
            cv2.putText(raw_frame, f"P1: {phase1_ms:.0f} ms", (10, 55),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 130, 255), 2)
            ok_raw, jpeg_raw = cv2.imencode('.jpg', raw_frame,
                                            [cv2.IMWRITE_JPEG_QUALITY, _MJPEG_QUALITY])

            # ── Base model annotated variant ──────────────────────────────────
            if base_results:
                _draw_results(base_frame, base_results)
            cv2.putText(base_frame, f"YOLOv8s Base", (10, 55),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (167, 139, 250), 2)
            ok_base, jpeg_base = cv2.imencode('.jpg', base_frame,
                                              [cv2.IMWRITE_JPEG_QUALITY, _MJPEG_QUALITY])

            # Write all variants atomically and wake every waiting HTTP generator
            with _jpeg_cache_cond:
                if ok_ann:
                    _jpeg_annotated = (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                                       + jpeg_ann.tobytes() + b'\r\n')
                if ok_raw:
                    _jpeg_raw = (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                                 + jpeg_raw.tobytes() + b'\r\n')
                if ok_base:
                    _jpeg_base = (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                                  + jpeg_base.tobytes() + b'\r\n')
                _jpeg_cache_version += 1
                _jpeg_cache_cond.notify_all()  # wake all HTTP generators instantly

        except Exception as e:
            print(f"[ERR] MJPEG encoder thread: {e}")
            time.sleep(0.1)

# ─── Inference Thread (YOLO) ──────────────────────────────────────────────────
def inference_thread():
    """
    Runs YOLO inference as fast as possible on the latest available frame.
    Frame deduplication skips frames already processed.
    """
    global detection_state, research_active, yolo_model

    print("[OK] Inference thread started.")

    infer_fps_frames = 0
    infer_fps_start  = time.time()
    last_frame_id    = -1

    while True:
        try:
            index_enabled = detection_state["enabled"]
            should_run = (index_enabled or research_active) and YOLO_AVAILABLE and (yolo_model is not None)

            if not should_run:
                time.sleep(0.1)
                continue

            # ── Wait for a new frame (zero-polling, OS condition variable) ────
            frame, frame_id = frame_manager.wait_for_new(last_frame_id, timeout=0.5)
            if frame is None or frame_id == last_frame_id:
                continue
            last_frame_id = frame_id

            conf = detection_state["confidence"]

            # ── YOLO inference (YOLOWorld) ─────────────────────────────────────
            with _infer_lock:   # guard against concurrent set_classes() reshaping the head
                results = yolo_model.track(frame, conf=conf, verbose=False, imgsz=_INFER_IMGSZ, persist=True)

            # ── Emit per-frame speed breakdown ────────────────────────────────
            if results and hasattr(results[0], 'speed') and results[0].speed:
                spd = results[0].speed
                _boxes = results[0].boxes
                _det_n = int(len(_boxes)) if _boxes is not None else 0
                _avg_c = round(float(_boxes.conf.mean().item()) if _det_n > 0 else 0.0, 3)
                _pre  = round(spd.get('preprocess',  0), 1)
                _inf  = round(spd.get('inference',   0), 1)
                _post = round(spd.get('postprocess', 0), 1)
                _tot  = round(sum(spd.values()),         1)
                socketio.emit('inference_speed', {
                    'model_key':       'worldv2',
                    'model_name':      _MODEL_FILENAME,
                    'preprocess_ms':   _pre,
                    'inference_ms':    _inf,
                    'postprocess_ms':  _post,
                    'total_ms':        _tot,
                    'imgsz':           _INFER_IMGSZ,
                    'detection_count': _det_n,
                    'avg_conf':        _avg_c,
                })
                with _scene_lock:
                    _scene_snap = _current_scene
                _names = results[0].names
                _cls_names = [
                    (_names.get(int(c), str(int(c))) if isinstance(_names, dict)
                     else (_names[int(c)] if 0 <= int(c) < len(_names) else str(int(c))))
                    for c in (_boxes.cls.cpu().numpy() if _boxes is not None else [])
                ]
                _log_yolo_infer('worldv2', _MODEL_FILENAME, _scene_snap,
                                _pre, _inf, _post, _tot,
                                _INFER_IMGSZ, _det_n, _avg_c, _cls_names)

            # ── Inference FPS counter ─────────────────────────────────────────
            infer_fps_frames += 1
            now_i = time.time()
            if now_i - infer_fps_start >= 1.0:
                infer_fps = infer_fps_frames / (now_i - infer_fps_start)
                infer_fps_frames = 0
                infer_fps_start  = now_i
                with state_lock:
                    robot_state['infer_fps'] = infer_fps

            # ── Parse results ─────────────────────────────────────────────────
            new_results = []
            if results:
                r     = results[0]
                names = r.names
                boxes = r.boxes
                if boxes is not None and len(boxes):
                    xyxy_all  = boxes.xyxy.cpu().numpy().astype(int)
                    cls_all   = boxes.cls.cpu().numpy().astype(int)
                    conf_all  = boxes.conf.cpu().numpy()
                    track_ids = boxes.id.cpu().numpy().astype(int) if boxes.id is not None else None
                    for i in range(len(boxes)):
                        cls_id   = int(cls_all[i])
                        cls_name = names.get(cls_id, str(cls_id)) if isinstance(names, dict) \
                                   else (names[cls_id] if 0 <= cls_id < len(names) else str(cls_id))
                        new_results.append({
                            "bbox":  xyxy_all[i].tolist(),
                            "class": cls_name,
                            "id":    int(track_ids[i]) if track_ids is not None else cls_id,
                            "conf":  float(conf_all[i]),
                        })

            # ── Update shared state ───────────────────────────────────────────
            with detection_lock:
                detection_state["last_results"] = new_results
                detection_state["detections"]   = [{"class": d["class"], "conf": d["conf"]}
                                                    for d in new_results]

            socketio.emit('detection_results', detection_state["detections"])
            _evaluate_alert_rules(new_results)

        except Exception as e:
            print(f"[ERR] Inference thread: {e}")
            time.sleep(0.1)

# ─── Base Model Inference Thread (parallel benchmark) ────────────────────────
def base_inference_thread():
    """
    Runs YOLOv8s base model inference in parallel with the WorldV2 thread.
    Stores results in _base_detection_results (drives video_feed_base).
    Uses its own lock so it never contends with WorldV2's _infer_lock / set_classes().
    """
    global research_active, _base_detection_results

    if _yolo_base_model is None:
        print("[INFO] Base inference thread: yolov8s.pt not loaded, exiting.")
        return

    last_frame_id = -1
    print("[OK] Base inference thread started.")

    while True:
        try:
            should_run = (detection_state["enabled"] or research_active) and (_yolo_base_model is not None)
            if not should_run:
                time.sleep(0.1)
                continue

            frame, frame_id = frame_manager.wait_for_new(last_frame_id, timeout=0.5)
            if frame is None or frame_id == last_frame_id:
                continue
            last_frame_id = frame_id

            conf = detection_state["confidence"]

            results = _yolo_base_model.track(frame, conf=conf, verbose=False, imgsz=_INFER_IMGSZ, persist=True)

            if not results:
                continue

            # ── Emit speed metrics ────────────────────────────────────────────
            if hasattr(results[0], 'speed') and results[0].speed:
                spd = results[0].speed
                _boxes = results[0].boxes
                _det_n = int(len(_boxes)) if _boxes is not None else 0
                _avg_c = round(float(_boxes.conf.mean().item()) if _det_n > 0 else 0.0, 3)
                _pre  = round(spd.get('preprocess',  0), 1)
                _inf  = round(spd.get('inference',   0), 1)
                _post = round(spd.get('postprocess', 0), 1)
                _tot  = round(sum(spd.values()),         1)
                socketio.emit('inference_speed', {
                    'model_key':       'base',
                    'model_name':      _BASE_MODEL_FILENAME,
                    'preprocess_ms':   _pre,
                    'inference_ms':    _inf,
                    'postprocess_ms':  _post,
                    'total_ms':        _tot,
                    'imgsz':           _INFER_IMGSZ,
                    'detection_count': _det_n,
                    'avg_conf':        _avg_c,
                })
                with _scene_lock:
                    _scene_snap = _current_scene
                _names = results[0].names
                _cls_names = [
                    (_names.get(int(c), str(int(c))) if isinstance(_names, dict)
                     else (_names[int(c)] if 0 <= int(c) < len(_names) else str(int(c))))
                    for c in (_boxes.cls.cpu().numpy() if _boxes is not None else [])
                ]
                _log_yolo_infer('base', _BASE_MODEL_FILENAME, _scene_snap,
                                _pre, _inf, _post, _tot,
                                _INFER_IMGSZ, _det_n, _avg_c, _cls_names)

            # ── Parse detections → store for video_feed_base ──────────────────
            r     = results[0]
            names = r.names
            boxes = r.boxes
            new_base_results = []
            if boxes is not None and len(boxes):
                xyxy_all  = boxes.xyxy.cpu().numpy().astype(int)
                cls_all   = boxes.cls.cpu().numpy().astype(int)
                conf_all  = boxes.conf.cpu().numpy()
                track_ids = boxes.id.cpu().numpy().astype(int) if boxes.id is not None else None
                for i in range(len(boxes)):
                    cls_id   = int(cls_all[i])
                    cls_name = names.get(cls_id, str(cls_id)) if isinstance(names, dict) \
                               else (names[cls_id] if 0 <= cls_id < len(names) else str(cls_id))
                    new_base_results.append({
                        "bbox":  xyxy_all[i].tolist(),
                        "class": cls_name,
                        "id":    int(track_ids[i]) if track_ids is not None else cls_id,
                        "conf":  float(conf_all[i]),
                    })
            with _base_detection_lock:
                _base_detection_results = new_base_results

            # Emit to research page so the detected-objects list updates in real-time
            socketio.emit('base_detection_results', new_base_results)

        except Exception as e:
            print(f"[ERR] Base inference thread: {e}")
            time.sleep(0.1)

# ─── System Monitor & Main Logic Thread ───────────────────────────────────────
def system_monitor_thread():
    """Calculates FPS and monitors resources."""
    monitoring_active = True
    frame_counter = 0
    start_time = time.time()
    
    while monitoring_active:
        time.sleep(1.0)
        
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        temp = 0.0
        try:
            temps = psutil.sensors_temperatures()
            if 'cpu_thermal' in temps: temp = temps['cpu_thermal'][0].current
            elif 'coretemp' in temps: temp = temps['coretemp'][0].current
        except: pass
        
        with state_lock:
            fps       = robot_state.get('fps', 0.0)
            infer_fps = robot_state.get('infer_fps', 0.0)
            phase1_ms = robot_state.get('phase1_ms', 0.0)
            robot_state['cpu_usage'] = cpu
            robot_state['ram_usage'] = ram
            robot_state['cpu_temp'] = temp

        socketio.emit('system_stats', {
            'fps': round(fps, 1),
            'infer_fps': round(infer_fps, 1),
            'phase1_ms': phase1_ms,
            'cpu': cpu,
            'ram': ram,
            'temp': temp
        })

# Start Threads
if CV2_AVAILABLE:
    threading.Thread(target=camera_capture_thread,  daemon=True).start()
    threading.Thread(target=mjpeg_encoder_thread,   daemon=True).start()  # pre-encode frames
    threading.Thread(target=inference_thread,        daemon=True).start()
    threading.Thread(target=base_inference_thread,   daemon=True).start()
    threading.Thread(target=phase1_thread,           daemon=True).start()
    threading.Thread(target=system_monitor_thread,   daemon=True).start()

def _class_color(cls_id):
    """Return a distinct BGR color for each class index."""
    palette = [
        (66, 133, 244), (219, 68, 55), (244, 180, 0), (15, 157, 88),
        (171, 71, 188), (0, 172, 193), (255, 112, 67), (158, 157, 36),
        (121, 85, 72), (96, 125, 139),
    ]
    return palette[cls_id % len(palette)]

def _draw_results(img, results):
    if not results: return
    for d in results:
        x1, y1, x2, y2 = d['bbox']
        color = _class_color(d.get('id', -1) if d.get('id', -1) > -1 else hash(d['class']) % 80)
        label = f"{d['class']} {d.get('id','')}"
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        cv2.putText(img, label, (x1, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

def _make_blank_jpeg(text="Camera Offline / Loading..."):
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(img, text, (140, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    _, jpeg = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 50])
    return b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n'

def _stream_from_cache(cache_attr: str):
    """Event-driven MJPEG streamer: wakes exactly when the encoder produces a new frame.
    Eliminates polling drift and duplicate frame sends — each frame is yielded once."""
    if not CV2_AVAILABLE:
        return
    blank_bytes   = _make_blank_jpeg()
    last_version  = -1
    last_keepalive = 0.0
    try:
        while True:
            # Wait for encoder to signal a new frame (or 1 s timeout for keepalive).
            # IMPORTANT: check the return value — wait_for returns False on timeout,
            # meaning the predicate was NOT met.  Yielding on timeout would re-send
            # the old cached frame, causing the repeated-frame jitter the user sees.
            with _jpeg_cache_cond:
                changed = _jpeg_cache_cond.wait_for(
                    lambda: _jpeg_cache_version != last_version,
                    timeout=1.0
                )
                new_version = _jpeg_cache_version
                jpeg_bytes  = globals()[cache_attr]

            now = time.time()
            if jpeg_bytes is None or frame_manager.is_stale(timeout=10):
                # Camera stale — send a blank keepalive at most every 0.5 s
                if now - last_keepalive > 0.5:
                    yield blank_bytes
                    last_keepalive = now
                continue

            if not changed:
                # Timed out with no new frame — don't re-send the old frame
                continue

            last_version = new_version
            yield jpeg_bytes
    except GeneratorExit:
        pass  # client disconnected — clean exit

def generate_frames_index():
    yield from _stream_from_cache('_jpeg_annotated')

def generate_frames_research():
    yield from _stream_from_cache('_jpeg_annotated')

def generate_frames_raw():
    yield from _stream_from_cache('_jpeg_raw')

def generate_frames_base():
    yield from _stream_from_cache('_jpeg_base')


# ─── Sensor Polling Thread ────────────────────────────────────────────────────
def sensor_thread():
    while True:
        if not HARDWARE_AVAILABLE:
            time.sleep(1)
            continue
        try:
            car.Ctrl_Ulatist_Switch(1)
            time.sleep(0.05)
            diss_H = car.read_data_array(0x1b, 1)
            diss_L = car.read_data_array(0x1a, 1)
            if diss_H and diss_L:
                dist = (diss_H[0] << 8) | diss_L[0]
                with state_lock:
                    robot_state["ultrasonic_mm"] = dist

            track_data = car.read_data_array(0x0a, 1)
            if track_data:
                track = int(track_data[0])
                with state_lock:
                    robot_state["line_track"] = {
                        "x1": (track >> 3) & 0x01,
                        "x2": (track >> 2) & 0x01,
                        "x3": (track >> 1) & 0x01,
                        "x4": track & 0x01,
                    }
        except Exception:
            pass
        # Push sensor data to all connected clients
        with state_lock:
            sensors = {
                "ultrasonic_mm": robot_state["ultrasonic_mm"],
                "line_track": robot_state["line_track"],
                "ir_value": robot_state["ir_value"],
            }
        socketio.emit('sensors', sensors)
        time.sleep(0.3)


# ─── Status Broadcast Thread ─────────────────────────────────────────────────
def status_broadcast_thread():
    while True:
        with state_lock:
            data = dict(robot_state)
        socketio.emit('status', data)
        time.sleep(0.25)


# ─── Motor Helpers ────────────────────────────────────────────────────────────
def _ctrl(motor_id, motor_dir, motor_speed):
    if HARDWARE_AVAILABLE:
        car.Ctrl_Car(motor_id, motor_dir, motor_speed)

def _update_motor(name, d, s):
    robot_state["motors"][name]["dir"] = d
    robot_state["motors"][name]["speed"] = s

def go_straight(spd):
    _ctrl(0,0,spd); _ctrl(1,0,spd); _ctrl(2,0,spd); _ctrl(3,0,spd)
    with state_lock:
        for n in ("L1","L2","R1","R2"): _update_motor(n, 0, spd)
        robot_state["direction"] = "forward"

def go_back(spd):
    _ctrl(0,1,spd); _ctrl(1,1,spd); _ctrl(2,1,spd); _ctrl(3,1,spd)
    with state_lock:
        for n in ("L1","L2","R1","R2"): _update_motor(n, 1, spd)
        robot_state["direction"] = "backward"

def turn_left(spd):
    _ctrl(0,0,0); _ctrl(1,0,0); _ctrl(2,0,spd); _ctrl(3,0,spd)
    with state_lock:
        _update_motor("L1",0,0); _update_motor("L2",0,0)
        _update_motor("R1",0,spd); _update_motor("R2",0,spd)
        robot_state["direction"] = "turn_left"

def turn_right(spd):
    _ctrl(0,0,spd); _ctrl(1,0,spd); _ctrl(2,0,0); _ctrl(3,0,0)
    with state_lock:
        _update_motor("L1",0,spd); _update_motor("L2",0,spd)
        _update_motor("R1",0,0); _update_motor("R2",0,0)
        robot_state["direction"] = "turn_right"

def rotate_left(spd):
    _ctrl(0,1,spd); _ctrl(1,1,spd); _ctrl(2,0,spd); _ctrl(3,0,spd)
    with state_lock:
        _update_motor("L1",1,spd); _update_motor("L2",1,spd)
        _update_motor("R1",0,spd); _update_motor("R2",0,spd)
        robot_state["direction"] = "rotate_left"

def rotate_right(spd):
    _ctrl(0,0,spd); _ctrl(1,0,spd); _ctrl(2,1,spd); _ctrl(3,1,spd)
    with state_lock:
        _update_motor("L1",0,spd); _update_motor("L2",0,spd)
        _update_motor("R1",1,spd); _update_motor("R2",1,spd)
        robot_state["direction"] = "rotate_right"

def back_left(spd):
    _ctrl(0,0,0); _ctrl(1,0,0); _ctrl(2,1,spd); _ctrl(3,1,spd)
    with state_lock:
        _update_motor("L1",0,0); _update_motor("L2",0,0)
        _update_motor("R1",1,spd); _update_motor("R2",1,spd)
        robot_state["direction"] = "back_left"

def back_right(spd):
    _ctrl(0,1,spd); _ctrl(1,1,spd); _ctrl(2,0,0); _ctrl(3,0,0)
    with state_lock:
        _update_motor("L1",1,spd); _update_motor("L2",1,spd)
        _update_motor("R1",0,0); _update_motor("R2",0,0)
        robot_state["direction"] = "back_right"

def stop_all():
    _ctrl(0,0,0); _ctrl(1,0,0); _ctrl(2,0,0); _ctrl(3,0,0)
    with state_lock:
        for n in ("L1","L2","R1","R2"): _update_motor(n, 0, 0)
        robot_state["direction"] = "stopped"


# ─── Flask Routes ─────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/research')
def research_dashboard():
    return render_template('research.html')

@app.route('/research-log')
def research_log():
    return render_template('research-log.html')

def _ctx_authed():
    return session.get('ctx_authed') is True

@app.route('/manage-context')
def manage_context():
    if not _ctx_authed():
        return render_template('manage_context.html', show_login=True)
    return render_template('manage_context.html', show_login=False)

@app.route('/manage-context/login', methods=['POST'])
def manage_context_login():
    pw = request.get_json(force=True).get('password', '')
    if pw == ADMIN_PASSWORD:
        session['ctx_authed'] = True
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'Incorrect password'}), 401

@app.route('/manage-context/logout', methods=['POST'])
def manage_context_logout():
    session.pop('ctx_authed', None)
    return jsonify({'ok': True})

@app.route('/api/context/scenes', methods=['GET'])
def api_context_scenes():
    if not _ctx_authed():
        return jsonify({'error': 'Unauthorized'}), 401
    import sqlite3 as _sqlite3
    vocab = request.args.get('vocab', 'coco80').strip()
    table = 'scene_context_objects365' if vocab == 'objects365' else 'scene_context'
    db_path = os.path.join(os.path.dirname(__file__), 'data', 'context.db')
    conn = _sqlite3.connect(db_path)
    conn.row_factory = _sqlite3.Row
    cur = conn.cursor()
    q = request.args.get('q', '').strip().lower()
    if q:
        cur.execute(f'SELECT id, scene_name, yolo_classes, model_file FROM {table} WHERE lower(scene_name) LIKE ? ORDER BY scene_name', (f'%{q}%',))
    else:
        cur.execute(f'SELECT id, scene_name, yolo_classes, model_file FROM {table} ORDER BY scene_name')
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route('/api/context/scenes/<int:scene_id>', methods=['PUT'])
def api_context_update(scene_id):
    if not _ctx_authed():
        return jsonify({'error': 'Unauthorized'}), 401
    import sqlite3 as _sqlite3, json as _json
    data = request.get_json(force=True)
    yolo_classes = data.get('yolo_classes')
    model_file = data.get('model_file')
    if yolo_classes is None or model_file is None:
        return jsonify({'error': 'yolo_classes and model_file required'}), 400
    if isinstance(yolo_classes, list):
        yolo_classes = _json.dumps(yolo_classes)
    vocab = request.args.get('vocab', 'coco80').strip()
    table = 'scene_context_objects365' if vocab == 'objects365' else 'scene_context'
    db_path = os.path.join(os.path.dirname(__file__), 'data', 'context.db')
    conn = _sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(f'UPDATE {table} SET yolo_classes=?, model_file=? WHERE id=?',
                (yolo_classes, model_file, scene_id))
    if cur.rowcount == 0:
        conn.close()
        return jsonify({'error': 'not found'}), 404
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/context/scenes', methods=['POST'])
def api_context_create():
    if not _ctx_authed():
        return jsonify({'error': 'Unauthorized'}), 401
    import sqlite3 as _sqlite3, json as _json
    data = request.get_json(force=True)
    scene_name = (data.get('scene_name') or '').strip()
    yolo_classes = data.get('yolo_classes', [])
    model_file = data.get('model_file', 'yolov8s-worldv2.pt')
    if not scene_name:
        return jsonify({'error': 'scene_name required'}), 400
    if isinstance(yolo_classes, list):
        yolo_classes = _json.dumps(yolo_classes)
    vocab = request.args.get('vocab', 'coco80').strip()
    table = 'scene_context_objects365' if vocab == 'objects365' else 'scene_context'
    db_path = os.path.join(os.path.dirname(__file__), 'data', 'context.db')
    conn = _sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute(f'INSERT INTO {table} (scene_name, yolo_classes, model_file) VALUES (?,?,?)',
                    (scene_name, yolo_classes, model_file))
        conn.commit()
        new_id = cur.lastrowid
    except _sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'scene_name already exists'}), 409
    conn.close()
    return jsonify({'ok': True, 'id': new_id}), 201

@app.route('/api/context/scenes/<int:scene_id>', methods=['DELETE'])
def api_context_delete(scene_id):
    if not _ctx_authed():
        return jsonify({'error': 'Unauthorized'}), 401
    import sqlite3 as _sqlite3
    vocab = request.args.get('vocab', 'coco80').strip()
    table = 'scene_context_objects365' if vocab == 'objects365' else 'scene_context'
    db_path = os.path.join(os.path.dirname(__file__), 'data', 'context.db')
    conn = _sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(f'DELETE FROM {table} WHERE id=?', (scene_id,))
    if cur.rowcount == 0:
        conn.close()
        return jsonify({'error': 'not found'}), 404
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/context/models', methods=['GET'])
def api_context_models():
    if not _ctx_authed():
        return jsonify({'error': 'Unauthorized'}), 401
    models_dir = os.path.join(os.path.dirname(__file__), 'models')
    files = [f for f in os.listdir(models_dir) if f.endswith(('.pt', '.onnx'))]
    files.sort()
    return jsonify(files)

@app.route('/api/inference-history')
def api_inference_history():
    """
    Return the last N Phase 2 scene-switch records from the DB.
    Query params:
      limit  — max rows to return (default 50, max 200)
    """
    limit = min(int(request.args.get('limit', 50)), 200)
    try:
        with _db_lock:
            with sqlite3.connect(_db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    '''SELECT switch_id, ts, scene, mode, num_classes,
                              db_query_ms, switch_ms, total_ms, model_file
                       FROM inference_history
                       ORDER BY id DESC
                       LIMIT ?''',
                    (limit,)
                )
                rows = [dict(r) for r in cur.fetchall()]
        # Return newest-first (already ordered by id DESC)
        return jsonify({'records': rows, 'count': len(rows)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/phase1-history')
def api_phase1_history():
    """Return the last N Phase 1 scene predictions from the DB."""
    limit = min(int(request.args.get('limit', 50)), 200)
    try:
        with _db_lock:
            with sqlite3.connect(_db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    '''SELECT infer_id, ts, scene, confidence, inference_ms
                       FROM phase1_history
                       ORDER BY id DESC
                       LIMIT ?''',
                    (limit,)
                )
                rows = [dict(r) for r in cur.fetchall()]
        return jsonify({'records': rows, 'count': len(rows)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/yolo-log')
def api_yolo_log():
    """
    Query yolo_comparison_log.
    Query params:
      limit    — max rows returned (default 200, max 2000)
      model    — filter to 'worldv2' or 'base' (default: both)
      scene    — filter to a specific scene name
      since    — ISO timestamp lower bound (e.g. '2026-03-19T10:00:00')
    Returns newest rows first.
    """
    limit  = min(int(request.args.get('limit',  200)), 2000)
    model  = request.args.get('model',  None)
    scene  = request.args.get('scene',  None)
    since  = request.args.get('since',  None)
    where, params = [], []
    if model: where.append('model_key = ?');  params.append(model)
    if scene: where.append('scene = ?');      params.append(scene)
    if since: where.append('ts >= ?');        params.append(since)
    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''
    params.append(limit)
    try:
        with _db_lock:
            with sqlite3.connect(_db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    f'''SELECT id, ts, model_key, model_name, scene,
                               preprocess_ms, inference_ms, postprocess_ms, total_ms,
                               imgsz, detection_count, avg_conf, detections
                        FROM yolo_comparison_log
                        {where_sql}
                        ORDER BY id DESC
                        LIMIT ?''',
                    params
                )
                rows = [dict(r) for r in cur.fetchall()]
        return jsonify({'records': rows, 'count': len(rows)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/yolo-log/export.csv')
def api_yolo_log_csv():
    """Export the full yolo_comparison_log as a CSV file download."""
    model = request.args.get('model', None)
    scene = request.args.get('scene', None)
    since = request.args.get('since', None)
    where, params = [], []
    if model: where.append('model_key = ?'); params.append(model)
    if scene: where.append('scene = ?');     params.append(scene)
    if since: where.append('ts >= ?');       params.append(since)
    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''
    try:
        import io, csv
        with _db_lock:
            with sqlite3.connect(_db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    f'''SELECT id, ts, model_key, model_name, scene,
                               preprocess_ms, inference_ms, postprocess_ms, total_ms,
                               imgsz, detection_count, avg_conf, detections
                        FROM yolo_comparison_log
                        {where_sql}
                        ORDER BY id ASC''',
                    params
                )
                rows = cur.fetchall()
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['id','ts','model_key','model_name','scene',
                         'preprocess_ms','inference_ms','postprocess_ms','total_ms',
                         'imgsz','detection_count','avg_conf','detections'])
        for r in rows:
            writer.writerow(list(r))
        buf.seek(0)
        from flask import make_response
        resp = make_response(buf.getvalue())
        resp.headers['Content-Type'] = 'text/csv'
        resp.headers['Content-Disposition'] = 'attachment; filename="yolo_comparison_log.csv"'
        return resp
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/yolo-log/stats')
def api_yolo_log_stats():
    """Per-model aggregate statistics for dashboard summary."""
    since = request.args.get('since', None)
    where = 'WHERE ts >= ?' if since else ''
    params = [since] if since else []
    try:
        with _db_lock:
            with sqlite3.connect(_db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    f'''SELECT model_key,
                               COUNT(*)                       AS samples,
                               ROUND(AVG(inference_ms),  2)  AS avg_inference_ms,
                               ROUND(MIN(inference_ms),  2)  AS min_inference_ms,
                               ROUND(MAX(inference_ms),  2)  AS max_inference_ms,
                               ROUND(AVG(total_ms),      2)  AS avg_total_ms,
                               ROUND(AVG(detection_count),2) AS avg_detections,
                               ROUND(AVG(avg_conf),      3)  AS avg_confidence
                        FROM yolo_comparison_log
                        {where}
                        GROUP BY model_key''',
                    params
                )
                stats = {r['model_key']: dict(r) for r in cur.fetchall()}
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/yolo-log/clear', methods=['POST'])
def api_yolo_log_clear():
    """Delete all rows from yolo_comparison_log (requires auth)."""
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 403
    try:
        with _db_lock:
            with sqlite3.connect(_db_path) as conn:
                cur = conn.execute('DELETE FROM yolo_comparison_log')
                conn.commit()
                deleted = cur.rowcount
        return jsonify({'deleted': deleted})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/scenes')
def api_scenes():
    """Public endpoint — returns all scene names for the research page scene browser."""
    vocab = request.args.get('vocab', 'coco80')
    scenes = context_mgr.get_all_scenes(vocabulary=vocab)
    return jsonify([{'name': s['name'], 'class_count': len(s['classes'])} for s in scenes])

@app.route('/api/stream/ping')
def stream_ping():
    """Lightweight health-check used by the client-side stream watchdog."""
    stale = frame_manager.is_stale(timeout=10)
    return jsonify({
        'ok': True,
        'last_frame': round(frame_manager.last_update_time, 3),
        'stale': stale,
        'ts': round(time.time(), 3),
    })

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames_index(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/video_feed_research')
def video_feed_research():
    return Response(generate_frames_research(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/video_feed_raw')
def video_feed_raw():
    return Response(generate_frames_raw(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/video_feed_base')
def video_feed_base():
    return Response(generate_frames_base(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# ─── WebRTC Routes ────────────────────────────────────────────────────────────
@app.route('/webrtc/offer', methods=['POST'])
def webrtc_offer_route():
    """
    Client POSTs an SDP offer; server returns a complete SDP answer.
    Body JSON: { sdp, type, mode }
      mode: "raw"        — no overlay, lowest latency
            "annotated"  — YOLO bounding-box overlay drawn server-side
    """
    if not WEBRTC_AVAILABLE:
        return jsonify({"error": "aiortc not installed — run: pip install aiortc"}), 503

    data       = request.get_json(force=True) or {}
    offer_sdp  = data.get('sdp', '')
    offer_type = data.get('type', 'offer')
    mode       = data.get('mode', 'raw')

    if not offer_sdp:
        return jsonify({"error": "sdp required"}), 400
    if mode not in ('raw', 'annotated'):
        mode = 'raw'

    try:
        future = _aio.run_coroutine_threadsafe(
            _handle_webrtc_offer(offer_sdp, offer_type, mode),
            _webrtc_loop
        )
        result = future.result(timeout=15)
        return jsonify(result)
    except Exception as e:
        print(f"[WebRTC] Offer error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/webrtc/status')
def webrtc_status_route():
    return jsonify({
        "available": WEBRTC_AVAILABLE,
        "active_peers": len(_webrtc_pcs) if WEBRTC_AVAILABLE else 0,
    })

# ─── Socket.IO Events ────────────────────────────────────────────────────────
@socketio.on('connect')
def on_connect():
    sid = request.sid
    ip = request.remote_addr or request.environ.get('HTTP_X_FORWARDED_FOR', 'unknown')
    print(f'[WS] Client connected: {sid[:8]}... from {ip}')
    _log_access('connect', sid=sid, ip=ip)
    with state_lock:
        emit('status', dict(robot_state))
    with detection_lock:
        emit('detection_state', {
            "enabled": detection_state["enabled"],
            "confidence": detection_state["confidence"],
            "classes": detection_state["classes"],
            "yolo_available": YOLO_AVAILABLE,
            "detections": detection_state["detections"],
        })
    # Send alert rules state
    with alert_lock:
        emit('alert_rules_state', {'rules': list(alert_rules)})
    # Send Phase 2 mode
    emit('phase2_mode_state', {'mode': _phase2_mode})
    # Send benchmark availability (both models run simultaneously)
    emit('benchmark_model_state', {
        'available_base':   _yolo_base_model is not None,
        'base_model_name':  _BASE_MODEL_FILENAME,
        'world_model_name': _MODEL_FILENAME,
    })
    # Send auth state (not blocking — client shows unlock button)
    emit('auth_state', {'authenticated': False})

@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid
    ip = request.remote_addr or 'unknown'
    with auth_lock:
        authenticated_sessions.discard(sid)
    _log_access('disconnect', sid=sid, ip=ip)
    print(f'[WS] Client disconnected: {sid[:8]}...')

@socketio.on('authenticate')
def on_authenticate(data):
    password = data.get('password', '')
    sid = request.sid
    ip = request.remote_addr or request.environ.get('HTTP_X_FORWARDED_FOR', 'unknown')
    if password == ADMIN_PASSWORD:
        with auth_lock:
            authenticated_sessions.add(sid)
        emit('auth_result', {'success': True})
        _log_access('auth_success', sid=sid, ip=ip)
        print(f'[AUTH] Client {sid[:8]}... authenticated from {ip}')
    else:
        emit('auth_result', {'success': False, 'message': 'Incorrect password.'})
        _log_access('auth_fail', details=f'wrong password attempt', sid=sid, ip=ip)
        print(f'[AUTH] Client {sid[:8]}... failed auth from {ip}')

@socketio.on('move')
def on_move(data):
    if not _require_auth(): return
    direction = data.get('direction', 'stop')
    with state_lock:
        spd = robot_state["speed"]
    actions = {
        'forward': go_straight, 'backward': go_back,
        'left': rotate_left, 'right': rotate_right,
        'forward_left': turn_left, 'forward_right': turn_right,
        'backward_left': back_left, 'backward_right': back_right,
    }
    fn = actions.get(direction)
    if fn:
        fn(spd)
    else:
        stop_all()

@socketio.on('stop')
def on_stop():
    if not _require_auth(): return
    stop_all()

@socketio.on('servo')
def on_servo(data):
    if not _require_auth(): return
    servo_id = int(data.get('id', 1))
    angle = max(0, min(180, int(data.get('angle', 60))))
    if HARDWARE_AVAILABLE:
        car.Ctrl_Servo(servo_id, angle)
    with state_lock:
        if servo_id == 1:
            robot_state["w_angle"] = angle
        elif servo_id == 2:
            robot_state["h_angle"] = angle

@socketio.on('speed')
def on_speed(data):
    if not _require_auth(): return
    spd = max(0, min(255, int(data.get('speed', 40))))
    with state_lock:
        robot_state["speed"] = spd

@socketio.on('led')
def on_led(data):
    if not _require_auth(): return
    action = data.get('action', 'off')
    if HARDWARE_AVAILABLE:
        if action == 'on':
            color = int(data.get('color', 0))
            car.Ctrl_WQ2812_ALL(1, color)
            with state_lock:
                robot_state["led_state"] = "on"
                robot_state["led_color"] = color
        elif action == 'off':
            car.Ctrl_WQ2812_ALL(0, 0)
            with state_lock:
                robot_state["led_state"] = "off"
        elif action == 'brightness':
            r, g, b = int(data.get('r',0)), int(data.get('g',0)), int(data.get('b',0))
            car.Ctrl_WQ2812_brightness_ALL(r, g, b)
            with state_lock:
                robot_state["led_state"] = f"rgb({r},{g},{b})"
    else:
        with state_lock:
            robot_state["led_state"] = action

@socketio.on('buzzer')
def on_buzzer(data):
    if not _require_auth(): return
    state = int(data.get('state', 0))
    if HARDWARE_AVAILABLE:
        car.Ctrl_BEEP_Switch(state)
    with state_lock:
        robot_state["buzzer"] = bool(state)

@socketio.on('detection_toggle')
def on_detection_toggle(data):
    if not _require_auth(): return
    enabled = bool(data.get('enabled', False))
    with detection_lock:
        detection_state["enabled"] = enabled
        if not enabled:
            detection_state["detections"] = []
    print(f"[WS] Detection {'enabled' if enabled else 'disabled'}")

@socketio.on('detection_config')
def on_detection_config(data):
    if not _require_auth(): return
    if 'confidence' in data:
        conf = max(0.05, min(1.0, float(data['confidence'])))
        with detection_lock:
            detection_state["confidence"] = conf
    if 'classes' in data:
        classes = [c.strip() for c in data['classes'] if c.strip()]
        if not classes:
            emit('detection_class_update', {"success": False, "error": "No valid classes provided"})
            return
        if not YOLO_AVAILABLE:
            emit('detection_class_update', {"success": False, "error": "YOLO model not loaded"})
            return
        if not IS_WORLD_MODEL:
            # Non-World models use built-in classes — can't change dynamically
            emit('detection_class_update', {
                "success": False,
                "error": f"Model '{_MODEL_FILENAME}' uses built-in classes and doesn't support dynamic class changes. Only YOLOWorld models (e.g. yolov8s-worldv2.pt) support set_classes()."
            })
            print(f"[WARN] set_classes() not supported for {_MODEL_FILENAME}")
            return
        try:
            yolo_model.set_classes(classes)
            with detection_lock:
                detection_state["classes"] = classes
            print(f"[OK] Detection classes updated: {classes}")
            emit('detection_class_update', {"success": True, "classes": classes})
        except Exception as e:
            print(f"[ERROR] Failed to set classes: {e}")
            traceback.print_exc()
            emit('detection_class_update', {"success": False, "error": str(e)})


@socketio.on('alert_rules_sync')
def on_alert_rules_sync(data):
    """
    Full-replace alert rules from the client.
    data: { rules: [ { id, class_name, count_threshold, action_type, action_params, enabled }, ... ] }
    Auth not required — research page needs this without login.
    """
    VALID_ACTIONS = {'led_color', 'led_rgb', 'buzzer_on', 'buzzer_pattern'}
    incoming = data.get('rules', [])
    validated = []
    for r in incoming:
        if not isinstance(r, dict):
            continue
        if r.get('action_type') not in VALID_ACTIONS:
            continue
        validated.append({
            'id': str(r.get('id', '')),
            'class_name': str(r.get('class_name', '')),
            'count_threshold': max(1, int(r.get('count_threshold', 1))),
            'action_type': r['action_type'],
            'action_params': r.get('action_params', {}),
            'enabled': bool(r.get('enabled', True)),
        })

    with alert_lock:
        # Clear actions for removed or disabled rules
        old_ids = {r['id'] for r in alert_rules}
        new_ids = {r['id'] for r in validated if r['enabled']}
        removed_ids = old_ids - new_ids
        for rid in removed_ids:
            if rid in alert_active:
                # Find the old rule to undo its action
                for old_r in alert_rules:
                    if old_r['id'] == rid:
                        _execute_alert_action(old_r, activate=False)
                        break
                alert_active.pop(rid, None)
                alert_cooldown.pop(rid, None)
                socketio.emit('alert_clear', {'rule_id': rid})

        alert_rules.clear()
        alert_rules.extend(validated)

    socketio.emit('alert_rules_state', {'rules': validated})
    print(f"[Alert] Rules synced: {len(validated)} rules")

@socketio.on('set_scene')
def on_set_scene(data):
    """
    Switch context based on a scene name (Phase 2 trigger).
    data: {'scene': 'living_room'}
    """
    if not _require_auth(): return
    scene_name = data.get('scene', '').strip()
    if not scene_name:
        return
    # Update the tracked current scene so auto-switching doesn't immediately override
    with _scene_lock:
        global _current_scene
        _current_scene = scene_name
    _switch_scene(scene_name)

@socketio.on('set_phase2_mode')
def on_set_phase2_mode(data):
    """
    Switch Phase 2 behaviour between 'classes' and 'model' mode.
    data: {'mode': 'classes'|'model'}
    No auth required — research page uses this without login.
    """
    global _phase2_mode
    mode = data.get('mode', '').strip()
    if mode not in ('classes', 'model'):
        emit('phase2_mode_state', {'mode': _phase2_mode, 'error': 'Invalid mode'})
        return
    _phase2_mode = mode
    print(f"[Phase2] Mode set to: {_phase2_mode}")
    socketio.emit('phase2_mode_state', {'mode': _phase2_mode})

@socketio.on('set_context_vocab')
def on_set_context_vocab(data):
    """
    Switch context vocabulary between 'coco80' and 'objects365'.
    data: {'vocab': 'coco80'|'objects365'}
    No auth required — research page uses this without login.
    """
    global _context_vocab
    vocab = data.get('vocab', '').strip()
    if vocab not in ('coco80', 'objects365'):
        emit('context_vocab_state', {'vocab': _context_vocab, 'error': 'Invalid vocab'})
        return
    _context_vocab = vocab
    print(f"[Phase2] Context vocabulary set to: {_context_vocab}")
    socketio.emit('context_vocab_state', {'vocab': _context_vocab})

@socketio.on('get_context_vocab')
def on_get_context_vocab():
    emit('context_vocab_state', {'vocab': _context_vocab})

# ─── Context Management API ───────────────────────────────────────────────────
@socketio.on('get_all_contexts')
def on_get_all_contexts(data=None):
    if not _require_auth(): return
    vocab = (data or {}).get('vocab', _context_vocab)
    scenes = context_mgr.get_all_scenes(vocabulary=vocab)
    emit('all_contexts', scenes)

@socketio.on('save_context')
def on_save_context(data):
    # data: {scene_name, classes:[], model_file, vocab?}
    if not _require_auth(): return
    try:
        vocab = data.get('vocab', _context_vocab)
        context_mgr.update_scene(
            data['scene_name'],
            data['classes'],
            data.get('model_file'),
            vocabulary=vocab
        )
        emit('save_context_result', {'success': True})
        on_get_all_contexts({'vocab': vocab})
    except Exception as e:
        emit('save_context_result', {'success': False, 'error': str(e)})

@socketio.on('research_servo')
def on_research_servo(data):
    # Bypass auth as requested for Research page
    # if not _require_auth(): return 
    servo_id = int(data.get('id', 1))
    angle = max(0, min(180, int(data.get('angle', 60))))
    if HARDWARE_AVAILABLE:
        car.Ctrl_Servo(servo_id, angle)
    with state_lock:
        if servo_id == 1:
            robot_state["w_angle"] = angle
        elif servo_id == 2:
            robot_state["h_angle"] = angle

@socketio.on('join_research')
def on_join_research():
    global research_active
    print("[WS] Client joined research mode")
    research_active = True
    emit('context_vocab_state', {'vocab': _context_vocab})
    emit('phase2_mode_state', {'mode': _phase2_mode})

@socketio.on('leave_research')
def on_leave_research():
    global research_active
    print("[WS] Client left research mode")
    # Optional: check if other clients are there? For simplicity, we assume one.
    research_active = False
    with detection_lock:
        emit('detection_state', {
            "enabled": detection_state["enabled"],
            "confidence": detection_state["confidence"],
            "classes": detection_state["classes"],
            "yolo_available": YOLO_AVAILABLE,
            "detections": detection_state["detections"],
        })


# ─── Startup Logic ────────────────────────────────────────────────────────────
def start_background_tasks():
    print("=" * 50)
    print("  PENS-KAIT 2026 Robot Control Dashboard")
    print(f"  YOLO detection: {'available' if YOLO_AVAILABLE else 'unavailable'}")
    print("  Using WebSocket for real-time control")
    
    if HARDWARE_AVAILABLE:
        # Center servos on startup
        try:
            car.Ctrl_Servo(1, 90)
            car.Ctrl_Servo(2, 90)
        except Exception as e:
            print(f"[WARN] Servo init failed: {e}")

    # Start remaining background threads
    threading.Thread(target=sensor_thread, daemon=True).start()
    threading.Thread(target=status_broadcast_thread, daemon=True).start()
    print("=" * 50)

# Run startup tasks when imported (Production/Gunicorn) or run directly
start_background_tasks()

@socketio.on('start_logging')
def on_start_logging():
    perf_logger.start()
    emit('system_stats', {'logging': True})

@socketio.on('stop_logging')
def on_stop_logging():
    perf_logger.stop()
    emit('system_stats', {'logging': False})

if __name__ == '__main__':
    print("  Open http://<YOUR_IP>:5000 in a browser")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
