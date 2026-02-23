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
import traceback
import subprocess
import sqlite3
import numpy as np
import psutil
import csv
from datetime import datetime
from flask import Flask, render_template, Response, request
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
_MODEL_FILENAME = 'yolov8s-worldv2.pt'   # ← Change this to switch models
DEFAULT_CLASSES = ["person", "car", "clock", "bottle", "chair", "book", "cell phone", "scissor", "laptop", "tv", "cup", "remote", "mouse"]
# ──────────────────────────────────────────────────────────────────────────────

YOLO_AVAILABLE = False
IS_WORLD_MODEL = 'world' in _MODEL_FILENAME.lower()  # Only WorldV2 supports set_classes()
yolo_model = None
_model_path = os.path.join(os.path.dirname(__file__), 'models', _MODEL_FILENAME)

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

# ─── Phase 1 Model ──────────────────────────────────────────────────────────
phase1_model = None
try:
    phase1_model = Phase1Model(os.path.dirname(os.path.abspath(__file__)))
    print("[OK] Phase 1 (Places365) initialized.")
except Exception as e:
    print(f"[WARN] Phase 1 init failed: {e}")


# Detection state
detection_lock = threading.Lock()
detection_state = {
    "enabled": False,
    "confidence": 0.35,
    "classes": DEFAULT_CLASSES[:],
    "detections": [],  # current frame results
}

# ─── Context Manager ──────────────────────────────────────────────────────────
context_mgr = ContextManager()

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
    """Create access_log table if it doesn't exist."""
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
        conn.commit()
    print(f"[OK] Access log database: {_db_path}")

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
        self.last_update_time = 0

    def update(self, frame):
        with self.lock:
            self.raw_frame = frame
            self.last_update_time = time.time()

    def get(self):
        with self.lock:
            return self.raw_frame.copy() if self.raw_frame is not None else None

frame_manager = FrameManager()

# ─── Camera Thread (Capture Only) ─────────────────────────────────────────────
class LibCameraCapture:
    """Wrapper to use rpicam-vid/libcamera-vid via subprocess for Pi 5 CSI cameras."""
    def __init__(self, width=640, height=480, framerate=30):
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
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
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

    while True:
        try:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.1)
                continue
            
            # FPS Calculation
            fps_frames += 1
            now = time.time()
            if now - fps_start_time >= 1.0:
                fps = fps_frames / (now - fps_start_time)
                fps_frames = 0
                fps_start_time = now
                with state_lock:
                    robot_state['fps'] = fps
                
            # Draw FPS overlay directly on the capture frame
            cv2.putText(frame, f"Cam FPS: {fps:.1f}", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            frame_manager.update(frame)
            time.sleep(0.005) # Yield slightly
        except Exception as e:
            print(f"[ERR] Camera capture loop: {e}")
            time.sleep(1)

# ─── Inference Thread (YOLO) ──────────────────────────────────────────────────
def inference_thread():
    """Runs YOLO inference on the latest available frame."""
    global detection_state, research_active, yolo_model
    
    print("[OK] Inference thread started.")
    
    last_frame_time = 0
    
    while True:
        try:
            # Check if we should run
            index_enabled = detection_state["enabled"]
            should_run = (index_enabled or research_active) and YOLO_AVAILABLE and (yolo_model is not None)
            
            if not should_run:
                time.sleep(0.2)
                continue
                
            frame = frame_manager.get()
            if frame is None:
                time.sleep(0.1)
                continue
            
            # Don't re-process the exact same frame if we're faster than camera
            # (Simple timestamp check could be added to FrameManager, but simple sleep is ok)

            conf = detection_state["confidence"]
            
            # Inference
            results = yolo_model.predict(frame, conf=conf, verbose=False, imgsz=320)
            
            # Processing
            new_results = []
            if results:
                r = results[0]
                names = r.names
                boxes = r.boxes
                
                for box in boxes:
                    b = box.xyxy[0].cpu().numpy().astype(int)
                    cls_id = int(box.cls[0])
                    conf_val = float(box.conf[0])
                    
                    if isinstance(names, dict):
                        cls_name = names.get(cls_id, str(cls_id))
                    else:
                        cls_name = names[cls_id] if 0 <= cls_id < len(names) else str(cls_id)
                        
                    new_results.append({
                        "bbox": [int(b[0]), int(b[1]), int(b[2]), int(b[3])],
                        "class": cls_name,
                        "id": cls_id,
                        "conf": conf_val
                    })

            # Update Shared State
            with detection_lock:
                detection_state["last_results"] = new_results
                detection_state["detections"] = [{"class": d["class"], "conf": d["conf"]} for d in new_results]
                
            socketio.emit('detection_results', detection_state["detections"])

            # Limit Inference FPS to avoid burning CPU (e.g. 15-20ms)
            time.sleep(0.02)
            
            # ─── Phase 1 (Global Context) Inference ───
            if research_active and phase1_model is not None:
                # Run Phase 1 inference at a much slower rate (e.g. once per second)
                # to not choke YOLO detection
                now = time.time()
                if now - last_frame_time > 1.0:
                    last_frame_time = now
                    p1_results = phase1_model.predict(frame)
                    socketio.emit('phase1_result', p1_results)
                    
        except Exception as e:
            print(f"[ERR] Inference thread: {e}")
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
            fps = robot_state.get('fps', 0.0)
            robot_state['cpu_usage'] = cpu
            robot_state['ram_usage'] = ram
            robot_state['cpu_temp'] = temp
            
        socketio.emit('system_stats', {
            'fps': round(fps, 1),
            'cpu': cpu, 
            'ram': ram, 
            'temp': temp
        })

# Start Threads
if CV2_AVAILABLE:
    threading.Thread(target=camera_capture_thread, daemon=True).start()
    threading.Thread(target=inference_thread, daemon=True).start()
    threading.Thread(target=system_monitor_thread, daemon=True).start()

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

def generate_frames_index():
    if not CV2_AVAILABLE: return
    while True:
        frame = frame_manager.get()
        if frame is None:
            time.sleep(0.05)
            continue
            
        # Check if we need to draw overlays
        with detection_lock:
            results = detection_state.get("last_results", [])
            enabled = detection_state["enabled"]
            
        if enabled and results:
            _draw_results(frame, results)
            
        ok, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            frame_bytes = jpeg.tobytes()
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        time.sleep(0.033) # Cap at ~30 FPS streaming

def generate_frames_research():
    if not CV2_AVAILABLE: return
    while True:
        frame = frame_manager.get()
        if frame is None:
            time.sleep(0.05)
            continue
            
        # Always draw for research
        with detection_lock:
            results = detection_state.get("last_results", [])
            
        if results:
            _draw_results(frame, results)
            
        ok, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            frame_bytes = jpeg.tobytes()
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        time.sleep(0.033)

def generate_frames_raw():
    if not CV2_AVAILABLE: return
    while True:
        frame = frame_manager.get()
        if frame is None:
            time.sleep(0.05)
            continue
            
        ok, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            frame_bytes = jpeg.tobytes()
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        time.sleep(0.033)


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

@socketio.on('set_scene')
def on_set_scene(data):
    """
    Switch context based on a scene name (Phase 2 trigger).
    data: {'scene': 'living_room'}
    """
    global yolo_model, _MODEL_FILENAME, IS_WORLD_MODEL, YOLO_AVAILABLE

    if not _require_auth(): return
    scene_name = data.get('scene', '').strip()
    if not scene_name:
        return
    
    print(f"[Phase2] Switching context to scene: {scene_name}")
    
    # 1. Query Database for context
    # Returns {'classes': [...], 'model': 'foo.pt'}
    ctx = context_mgr.get_context_for_scene(scene_name)
    target_classes = ctx['classes']
    target_model_file = ctx['model']
    
    print(f"[Phase2] Context for '{scene_name}': Model={target_model_file}, Classes={target_classes}")

    # 2. Check if we need to switch models
    if target_model_file != _MODEL_FILENAME and target_model_file:
        new_model_path = os.path.join(os.path.dirname(__file__), 'models', target_model_file)
        if os.path.exists(new_model_path):
            try:
                print(f"[Phase2] Loading new model: {target_model_file}...")
                with detection_lock:
                    yolo_model = YOLO(new_model_path) # Reload model
                    _MODEL_FILENAME = target_model_file
                    IS_WORLD_MODEL = 'world' in _MODEL_FILENAME.lower()
                    YOLO_AVAILABLE = True
                print(f"[Phase2] Model switched to {_MODEL_FILENAME}")
            except Exception as e:
                print(f"[ERROR] Failed to load model {target_model_file}: {e}")
                emit('model_update_error', {'error': str(e)})
                # Fallback to existing model logic...
        else:
            print(f"[WARN] Model file {target_model_file} not found! Keeping current model.")
    
    # 3. Update Classes (if supported)
    if YOLO_AVAILABLE:
        try:
            if IS_WORLD_MODEL:
                yolo_model.set_classes(target_classes)
                print(f"[OK] set_classes called on {_MODEL_FILENAME}")
            else:
                print(f"[INFO] {_MODEL_FILENAME} uses fixed classes (not World model).")

            with detection_lock:
                detection_state["classes"] = target_classes
                # Auto-enable detection when scene is set
                detection_state["enabled"] = True
            
            emit('detection_class_update', {"success": True, "classes": target_classes})
            emit('detection_state', { # Broadcast new state including enabled=True
                "enabled": True,
                "confidence": detection_state["confidence"],
                "classes": target_classes,
                "yolo_available": YOLO_AVAILABLE,
                "detections": detection_state["detections"],
            })
            emit('context_switched', {
                "scene": scene_name, 
                "classes": target_classes,
                "model": _MODEL_FILENAME
            })
        except Exception as e:
            print(f"[ERROR] Context switch failed: {e}")
            emit('detection_class_update', {"success": False, "error": str(e)})

# ─── Context Management API ───────────────────────────────────────────────────
@socketio.on('get_all_contexts')
def on_get_all_contexts():
    if not _require_auth(): return
    scenes = context_mgr.get_all_scenes()
    emit('all_contexts', scenes)

@socketio.on('save_context')
def on_save_context(data):
    # data: {scene_name, classes:[], model_file}
    if not _require_auth(): return
    try:
        context_mgr.update_scene(
            data['scene_name'], 
            data['classes'], 
            data.get('model_file')
        )
        emit('save_context_result', {'success': True})
        on_get_all_contexts() # Refresh list
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
    print("  Open http://<YOUR_IP>:5001 in a browser (Development Mode)")
    socketio.run(app, host='0.0.0.0', port=5001, debug=False, allow_unsafe_werkzeug=True)
