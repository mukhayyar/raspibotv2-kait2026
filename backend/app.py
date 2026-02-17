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
import sqlite3
from flask import Flask, render_template, Response, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv

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
DEFAULT_CLASSES = ["person", "car", "dog", "cat", "bottle"]
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

# Detection state
detection_lock = threading.Lock()
detection_state = {
    "enabled": False,
    "confidence": 0.35,
    "classes": DEFAULT_CLASSES[:],
    "detections": [],  # current frame results
}

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
    "w_angle": 90,
    "h_angle": 90,
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

# ─── Camera Streaming ─────────────────────────────────────────────────────────
output_frame = None
frame_lock = threading.Lock()


def camera_thread():
    global output_frame
    if not CV2_AVAILABLE:
        return
    try:
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        time.sleep(2)
        print("[OK] Camera started.")
        frame_count = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue

            # Run YOLO tracking every 3rd frame when enabled
            with detection_lock:
                det_enabled = detection_state["enabled"]
                det_conf = detection_state["confidence"]
                # Use stored result buffer if available
                last_results = detection_state.get("last_results", [])
                
            if det_enabled and YOLO_AVAILABLE:
                # 1. Run inference every N frames
                if frame_count % 3 == 0:
                    try:
                        # Use track() for ID assignment + persist=True
                        results = yolo_model.track(
                            frame, conf=det_conf, verbose=False,
                            persist=True, tracker="bytetrack.yaml",
                            imgsz=320
                        )
                        det_list = []
                        for r in results:
                            for box in r.boxes:
                                x1, y1, x2, y2 = box.xyxy[0].tolist()
                                conf = float(box.conf[0])
                                cls_id = int(box.cls[0])
                                # Track ID might be None if no update
                                track_id = int(box.id[0]) if box.id is not None else -1
                                cls_name = r.names.get(cls_id, str(cls_id))
                                
                                det_list.append({
                                    "class": cls_name,
                                    "id": track_id,
                                    "confidence": round(conf, 2),
                                    "bbox": [int(x1), int(y1), int(x2), int(y2)],
                                })
                        
                        # Update shared state and local buffer
                        with detection_lock:
                            detection_state["detections"] = det_list
                            detection_state["last_results"] = det_list
                            last_results = det_list # update local reference for drawing
                            
                        # Push updates only on new detection
                        socketio.emit('detection_results', det_list)
                    except Exception as e:
                        print(f"[ERROR] YOLO error: {e}")
                
                # 2. ALWAYS draw the LAST known results (zero-order hold) to stop blinking
                for d in last_results:
                    x1, y1, x2, y2 = d['bbox']
                    cls_name = d['class']
                    conf = d['confidence']
                    tid = d.get('id', -1)
                    
                    # Determine color: use Track ID for color stability if available
                    color_idx = tid if tid > -1 else hash(cls_name) % 80
                    color = _class_color(color_idx)
                    
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    
                    label = f"{cls_name} {tid if tid > -1 else ''} {conf:.0%}"
                    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                    cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
                    cv2.putText(frame, label, (x1 + 2, y1 - 4),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

            frame_count += 1
            with frame_lock:
                output_frame = frame.copy()
            time.sleep(0.033)
    except Exception as e:
        print(f"[WARN] Camera unavailable: {e}")


def _class_color(cls_id):
    """Return a distinct BGR color for each class index."""
    palette = [
        (66, 133, 244), (219, 68, 55), (244, 180, 0), (15, 157, 88),
        (171, 71, 188), (0, 172, 193), (255, 112, 67), (158, 157, 36),
        (121, 85, 72), (96, 125, 139),
    ]
    return palette[cls_id % len(palette)]


def generate_frames():
    global output_frame
    if not CV2_AVAILABLE:
        return
    while True:
        with frame_lock:
            if output_frame is None:
                time.sleep(0.05)
                continue
            ok, jpeg = cv2.imencode('.jpg', output_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if not ok:
                continue
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

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
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
    angle = max(0, min(180, int(data.get('angle', 90))))
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

@socketio.on('detection_status')
def on_detection_status():
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

    # Start background threads
    threading.Thread(target=camera_thread, daemon=True).start()
    threading.Thread(target=sensor_thread, daemon=True).start()
    threading.Thread(target=status_broadcast_thread, daemon=True).start()
    print("=" * 50)

# Run startup tasks when imported (Production/Gunicorn) or run directly
start_background_tasks()

if __name__ == '__main__':
    print("  Open http://<YOUR_IP>:5000 in a browser (Development Mode)")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)

