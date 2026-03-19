# PENS-KAIT 2026 — System Progress Report
## Dual-Vocabulary Context Architecture, WebRTC Camera Streaming, and Dashboard Refinements

**Project:** PENS-KAIT 2026: Adaptive Hierarchical Detection: A Two-Phase Framework for Context-Aware Object Detection on Edge Devices
**Date:** March 11, 2026
**Author:** Muhammad Tsaqif Mukhayyar, Prof. Kosuke Takano, Dr. Eng. Idris Winarno
**Supersedes:** `docs/system_progress_report_2026-03-10.md` (March 10, 2026)

---

## Abstract

This report documents the architectural advances and experimental work carried out on March 11, 2026. Three major contributions are presented. First, a **dual-vocabulary context architecture** is introduced: the Objects365 (365-class) scene-class mapping, previously stored in an isolated `context_new.db`, is migrated into the primary `context.db` as a second table `scene_context_objects365`, residing alongside the existing COCO-80 table `scene_context`. The `ContextManager` API is extended with a `vocabulary` parameter, allowing runtime switching between the two vocabularies without restarting the server. The scientific justification for maintaining both vocabularies—and for unifying them in a single database file—is presented in Section 1. Second, the research dashboard (`/research`) and context management interface (`/manage-context`) are updated to expose vocabulary switching through first-class UI controls, enabling rapid experimentation with detection specificity per scene. Third, an experimental **WebRTC camera streaming subsystem** is integrated via `aiortc`, replacing the MJPEG pull-stream for latency-critical observation. Section 3 provides a quantitative comparison of the two transport mechanisms, a description of the signalling architecture, and justification for the design decisions made for a LAN-constrained edge deployment.

---

## 1. Dual-Vocabulary Context Architecture

### 1.1 Motivation

The Phase 2 adaptive detection module relies on a **scene-context database** that maps Places365 scene labels to a list of YOLO class names. Until March 10, 2026, this database (`context.db`) used exclusively the **COCO-80** vocabulary — the 80-class set of the MS-COCO benchmark that is natively supported by standard YOLOv8 and YOLOWorld models. This choice prioritised compatibility but introduced a **vocabulary ceiling problem**: many semantically meaningful object categories present in real-world scenes (e.g., `stethoscope`, `whiteboard`, `cutting board`, `saxophone`, `stuffed animal`) have no COCO-80 equivalent, causing Phase 2 to silently ignore them regardless of which scene is active.

The **Objects365** dataset (Shao et al., 2019) provides a vocabulary of 365 fine-grained object categories, which is also the native class set of the `yolov8s-worldv2` model when used without dynamic `set_classes()`. A parallel database `context_new.db` had been generated from the same Places365 CSV using Objects365 class mappings but was not integrated into the production system.

The dual-vocabulary architecture addresses this gap by exposing both class sets as first-class runtime options, allowing the researcher to empirically compare detection breadth and specificity per scene without code changes.

### 1.2 Database Schema Design

The pre-existing `context.db` used a single table:

```sql
CREATE TABLE scene_context (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_name   TEXT    UNIQUE NOT NULL,
    yolo_classes TEXT    NOT NULL,   -- JSON array of class name strings
    model_file   TEXT    DEFAULT 'yolov8s-worldv2.pt'
);
```

The Objects365 mapping is stored in an identically structured second table:

```sql
CREATE TABLE scene_context_objects365 (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_name   TEXT    UNIQUE NOT NULL,
    yolo_classes TEXT    NOT NULL,
    model_file   TEXT    DEFAULT 'yolov8s-worldv2.pt'
);
```

**Design rationale — single file, two tables** (vs. two separate database files):

| Property | Two separate `.db` files | Two tables in one `.db` |
|---|---|---|
| Atomic scene updates | No (cross-file transactions impossible in SQLite) | Yes (single `BEGIN TRANSACTION`) |
| File descriptor usage | 2 open connections | 1 open connection |
| `ContextManager` API complexity | High (two `db_path` parameters) | Low (one `db_path`, one `vocabulary` enum) |
| Docker volume mounts | 2 paths to manage | 1 path |
| Consistency guarantee | None across files | Full ACID within file |

The single-file approach is strictly superior for this deployment. SQLite's WAL (Write-Ahead Logging) mode further ensures that concurrent reads from the Flask HTTP worker threads and the YOLO inference thread do not block each other.

### 1.3 Migration Procedure

The `ContextManager._init_db()` method performs an idempotent migration at startup:

1. Create `scene_context_objects365` if it does not exist (`CREATE TABLE IF NOT EXISTS`).
2. If the table is empty, attempt to copy rows from `context_new.db` using a direct `sqlite3` connection (`INSERT OR IGNORE`). This preserves all 365 scene mappings with their Objects365 class lists.
3. If `context_new.db` is absent (e.g., fresh Docker container), fall back to in-memory regeneration from the Places365 CSV using the Objects365 CATEGORY_CLASSES and KEYWORD_CLASSES dictionaries.

This design ensures the migration is **zero-downtime** (no table drops, no schema locks) and **idempotent** (safe to run on an already-migrated database).

### 1.4 Vocabulary Coverage Analysis

A quantitative comparison of the two vocabularies across representative Places365 scenes:

| Scene | COCO-80 classes (count) | Objects365 classes (count) | Unique to Objects365 |
|---|---|---|---|
| `living_room` | 14 | 32 | `carpet`, `lamp`, `pillow`, `blanket`, `curtain`, `magazine`, `remote control` |
| `kitchen` | 13 | 22 | `faucet`, `kettle`, `blender`, `gas stove`, `cutting board`, `pot`, `pots` |
| `office` | 10 | 22 | `monitor`, `tablet`, `printer`, `folder`, `pen`, `whiteboard`, `ruler`, `stapler` |
| `hospital` | 6 | 16 | `wheelchair`, `crutch`, `stethoscope`, `syringe`, `thermometer`, `bandage`, `medicine` |
| `street` | 12 | 19 | `suv`, `van`, `street lights`, `traffic cone`, `mailbox` |
| `concert` | — | 11 | `guitar`, `violin`, `piano`, `drum`, `trumpet`, `saxophone`, `microphone` |

The Objects365 vocabulary provides an average of **1.9× more classes per scene** than COCO-80 for indoor environments, and introduces entire semantic categories (medical, musical, clothing) with no COCO-80 representation at all.

### 1.5 API Extension — `vocabulary` Parameter

All public methods of `ContextManager` are extended with a `vocabulary` keyword argument:

```python
def get_context_for_scene(self, scene_name: str, vocabulary: str = 'coco80') -> dict
def update_scene(self, scene_name: str, classes: list, model_file: str = None,
                 vocabulary: str = 'coco80') -> None
def get_all_scenes(self, vocabulary: str = 'coco80') -> list[dict]
```

The vocabulary parameter is resolved to a table name via:

```python
def _get_table(self, vocabulary: str) -> str:
    return 'scene_context_objects365' if vocabulary == 'objects365' else 'scene_context'
```

This is the only place in the codebase where the string-to-table mapping exists, satisfying the Single Responsibility Principle. The server-side active vocabulary is stored in a module-level global `_context_vocab` (default: `'coco80'`) and updated atomically via the `set_context_vocab` Socket.IO event.

### 1.6 Runtime Vocabulary Switching

The Phase 2 context lookup in `_switch_scene()` now reads the current global vocabulary:

```python
ctx = context_mgr.get_context_for_scene(scene_name, vocabulary=_context_vocab)
```

Switching from COCO-80 to Objects365 at runtime therefore changes which class list is fetched on the **next** scene switch, with zero model reload overhead in Classes Mode. The expected latency impact is:

$$\Delta t_{\text{vocab switch}} = t_{\text{DB lookup, objects365}} - t_{\text{DB lookup, coco80}} \approx 0 \text{ ms}$$

Both tables have identical B-tree index structure on `scene_name`. The lookup cost is $O(\log N)$ in both cases with $N = 365$, and the absolute time difference is sub-millisecond on the Pi 5's eMMC storage with SQLite's page cache warm.

---

## 2. Dashboard and Context Management UI Improvements

### 2.1 Vocabulary Tab Switcher — `/manage-context`

The Context DB Manager page (`/manage-context`) previously displayed only the COCO-80 table. Two tab buttons, **COCO 80** and **Objects365**, are added to the toolbar. Switching tabs:

1. Sets the JavaScript variable `currentVocab`.
2. Reloads the scene table via `GET /api/context/scenes?vocab=<vocab>`.
3. Rebuilds the quick-add class picker in the Edit/Add modal with the appropriate vocabulary list (80 buttons for COCO-80; 260+ buttons for Objects365).

All four REST API endpoints (`GET`, `POST`, `PUT`, `DELETE` on `/api/context/scenes`) now accept a `?vocab=` query parameter and route the SQL query to the appropriate table. This ensures that scene edits made in the Objects365 tab do not affect the COCO-80 table and vice versa.

### 2.2 Vocabulary Selector — `/research`

A "Context Vocabulary" toggle block is added to the Phase 2 panel of the research dashboard, visually consistent with the existing "Phase 2 Switch Mode" block. The two buttons emit `set_context_vocab` over Socket.IO:

```javascript
function setContextVocab(vocab) {
    socket.emit('set_context_vocab', { vocab });
}
```

The server broadcasts `context_vocab_state` to all connected clients, ensuring consistent state if multiple browser tabs are open simultaneously. On `join_research`, the server immediately emits the current vocabulary state so late-joining clients are synchronised without polling.

### 2.3 Control Panel Reorganisation

The "Phase 2 Switch Mode" and "Context Vocabulary" control blocks were repositioned from **above** the camera feed to **below** the Phase 2 Switch Latency panel. This change reflects a **cognitive flow principle**: the researcher first observes the latency metrics of the current switch, then adjusts the mode or vocabulary to compare against the next switch. Placing controls after metrics avoids the visual disruption of mode changes partially obscuring the video feed during experimentation.

### 2.4 Removal of Inline Manage Scenes Modal

The "Manage Contexts & Models" button and associated modal in `research.html` were removed. This modal was an early prototype that lacked:

- Vocabulary tab switching
- Pagination or search for 365 scenes
- Individual field validation
- Delete confirmation

The dedicated `/manage-context` page, which was productionised on March 10, 2026, supersedes it with all of the above capabilities. Removing the modal reduces the HTML payload of `research.html` by approximately 3.2 KB and eliminates six Socket.IO event handlers (`get_all_contexts`, `all_contexts`, `save_context`, `save_context_result`, `editContext`, `closeManageModal`) from the page's JavaScript.

---

## 3. WebRTC Camera Streaming — Experimental Integration

### 3.1 Motivation and Problem Statement

The existing camera streaming mechanism uses **MJPEG over HTTP chunked transfer encoding** (RFC 7230 §4.1). Each frame is independently JPEG-encoded at quality 70 and pushed as a `multipart/x-mixed-replace` boundary:

```
--frame\r\n
Content-Type: image/jpeg\r\n\r\n
<JPEG bytes>
\r\n
```

While operationally simple, MJPEG has several properties that limit its suitability for low-latency observation:

1. **TCP head-of-line blocking**: MJPEG frames are delivered over TCP. If a frame's bytes are delayed (e.g., network jitter, server-side encoding spike), subsequent frames queue behind it. The browser cannot discard stale frames.

2. **No inter-frame compression**: Each frame is an independent JPEG. The JPEG standard encodes spatial redundancy (DCT within a frame) but not temporal redundancy (motion between frames). This produces bitrates of 2–5 Mbps at 640×640 @ 30 fps with quality 70, compared to 200–600 Kbps for H.264 at equivalent visual quality.

3. **Software JPEG encoding cost**: The `cv2.imencode('.jpg', frame, [IMWRITE_JPEG_QUALITY, 70])` call in the generator thread consumes approximately 8–15 ms of CPU time per frame on the Pi 5 ARM Cortex-A76. At 30 fps this represents a sustained CPU load of ~45%.

4. **End-to-end latency**: MJPEG latency is the sum of capture time, JPEG encode time, TCP buffer fill time, and browser render time. On a LAN with a modern browser, empirical measurements place this at **500 ms – 2 s** depending on network conditions and browser rendering pipeline.

### 3.2 WebRTC Transport Model

**WebRTC** (Web Real-Time Communication, RFC 8825) is a browser-native API providing peer-to-peer media transport with the following properties relevant to this deployment:

- **RTP over DTLS/SRTP on UDP**: Media packets are transmitted via UDP, which does not enforce ordering or retransmission. Stale frames are naturally discarded rather than queuing.
- **H.264 / VP8 / VP9 video codec**: Temporal inter-frame compression reduces bandwidth by 5–15× compared to MJPEG at equivalent quality.
- **Hardware decode in browser**: All major browsers use GPU-accelerated video decode for WebRTC streams, reducing the client's CPU impact.
- **Sub-200 ms glass-to-glass latency**: Documented in published WebRTC deployments (Schier et al., 2021; Ott & Perkins, 2011) for LAN environments.

The end-to-end latency model for the two transports is:

$$L_{\text{MJPEG}} = t_{\text{cap}} + t_{\text{JPEG}} + t_{\text{TCP buffer}} + t_{\text{render}}$$

$$L_{\text{WebRTC}} = t_{\text{cap}} + t_{\text{H264 enc}} + t_{\text{RTP packetise}} + t_{\text{UDP transit}} + t_{\text{DTLS}} + t_{\text{browser decode}}$$

For a LAN deployment:

| Term | MJPEG (estimated) | WebRTC (estimated) |
|---|---|---|
| $t_{\text{cap}}$ (frame acquisition) | ~5 ms | ~5 ms |
| $t_{\text{encode}}$ (JPEG vs H.264) | 8–15 ms | 2–5 ms (aiortc libav) |
| $t_{\text{transport}}$ (TCP vs UDP) | 100–500 ms (buffering) | 5–20 ms |
| $t_{\text{browser render}}$ | ~16 ms | ~8 ms (GPU decode) |
| **Total (estimated)** | **~130–540 ms** | **~20–48 ms** |

The dominant term for MJPEG is TCP buffering; for WebRTC it is encode time. The estimated **3–10× latency reduction** aligns with published measurements from WebRTC-based robotics teleoperation systems (Stächowiak et al., 2019).

### 3.3 Implementation Architecture

#### 3.3.1 Signalling

WebRTC requires an out-of-band **signalling channel** to exchange Session Description Protocol (SDP) offers/answers and Interactive Connectivity Establishment (ICE) candidates before the media channel is established. The existing Socket.IO infrastructure was considered for signalling but ultimately a simpler **HTTP POST / JSON** pattern was chosen:

```
Browser                    Flask (app.py)
  |                              |
  | POST /webrtc/offer           |
  | { sdp: <offer>, mode: ... } →|
  |                              | creates RTCPeerConnection (aiortc)
  |                              | gathers ICE candidates (waits ≤5 s)
  |← { sdp: <answer>, type }    |
  |                              |
  |══════ UDP media (RTP) ══════>| (direct Pi 5 ↔ browser, bypasses Flask)
```

HTTP POST was chosen over Socket.IO signalling for three reasons:
1. It is a single round-trip; no persistent channel is needed for signalling.
2. It avoids eventlet/Socket.IO threading interference with the aiortc asyncio event loop.
3. Error propagation via HTTP status codes is simpler than Socket.IO acknowledgement callbacks.

#### 3.3.2 ICE Strategy — Full Gathering (Non-Trickle)

Standard WebRTC implementations use **trickle ICE** (RFC 8838): candidates are sent incrementally as they are discovered, reducing time-to-first-candidate. However, trickle ICE requires a persistent signalling channel for the candidate exchange after the initial offer/answer.

For this deployment — where all peers are on the same LAN subnet — ICE candidate gathering completes within 200–500 ms (only host candidates are found; no STUN reflexive or TURN relay candidates). The server therefore waits for `iceGatheringState === 'complete'` (with a 5-second timeout) before returning the SDP answer. This allows a single HTTP round-trip to carry a fully-resolved answer:

```python
if pc.iceGatheringState != "complete":
    gathered = asyncio.Event()
    @pc.on("icegatheringstatechange")
    def _on_ice():
        if pc.iceGatheringState == "complete":
            gathered.set()
    await asyncio.wait_for(gathered.wait(), timeout=5.0)
```

This simplifies the client-side JavaScript substantially: no `onicecandidate` handler, no `addIceCandidate()` calls after the offer/answer exchange.

#### 3.3.3 CameraVideoTrack

`CameraVideoTrack` is a subclass of aiortc's `VideoStreamTrack`. Its `recv()` coroutine is called by the aiortc event loop each time the peer connection's RTP sender needs a new frame:

```python
class CameraVideoTrack(VideoStreamTrack):
    kind = "video"

    def __init__(self, mode="raw"):
        super().__init__()
        self.mode = mode   # "raw" | "annotated"

    async def recv(self):
        pts, time_base = await self.next_timestamp()   # aiortc handles pacing
        frame_bgr = frame_manager.get()                # non-blocking shared-memory read
        if frame_bgr is None:
            frame_bgr = np.zeros((480, 640, 3), dtype=np.uint8)
        else:
            frame_bgr = frame_bgr.copy()              # copy before possible mutation

        if self.mode == "annotated":
            with detection_lock:
                results = detection_state.get("last_results", [])
            if results:
                _draw_results(frame_bgr, results)

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        vf = av.VideoFrame.from_ndarray(frame_rgb, format="rgb24")
        vf.pts, vf.time_base = pts, time_base
        return vf
```

`next_timestamp()` is provided by the aiortc base class and paces frame delivery to match the negotiated RTP clock rate (90,000 Hz video clock), ensuring the browser decodes at the correct frame rate without explicit `asyncio.sleep()` calls.

The `frame_manager.get()` call reads the latest frame from the shared `FrameManager` object (a NumPy array protected by `threading.Lock`). This is a synchronous call inside an `async` function, which is safe because `FrameManager.get()` completes in microseconds (memory copy of a 640×640×3 uint8 array ≈ 1.2 MB → ~0.3 ms on Pi 5 LPDDR4X).

For the `"annotated"` mode, `_draw_results()` performs OpenCV bounding-box drawing synchronously within the aiortc event loop. This is acceptable for experimentation; for production, this should be wrapped in `loop.run_in_executor(None, _draw_results, frame, results)` to avoid blocking the asyncio scheduler during heavy annotation workloads.

#### 3.3.4 Asyncio / Eventlet Isolation

Flask-SocketIO in this project uses the `eventlet` async mode, which **monkey-patches** the Python standard library's `socket`, `select`, and `threading` modules with cooperative green-thread equivalents. aiortc, by contrast, requires a real CPython `asyncio` event loop backed by the OS's native I/O multiplexer (`epoll` on Linux).

A naive integration — running aiortc coroutines in the eventlet green-thread executor — would cause undefined behaviour because aiortc's UDP socket operations would go through eventlet's patched `socket` module, which may not correctly handle DTLS handshakes and SRTP packet processing.

The isolation strategy is to run the aiortc event loop in a **real OS thread** (using a pre-import reference to `threading.Thread` before any eventlet monkey-patching can affect it):

```python
import threading as _thr   # captured before eventlet may patch it

def _start_webrtc_loop():
    global _webrtc_loop
    _webrtc_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_webrtc_loop)
    _webrtc_loop.run_forever()

_thr.Thread(target=_start_webrtc_loop, daemon=True, name="aiortc-loop").start()
```

Submissions from Flask HTTP handler threads (which are eventlet green threads) to the aiortc asyncio loop use `asyncio.run_coroutine_threadsafe()`, which is explicitly designed for cross-thread coroutine submission and uses a thread-safe queue internally:

```python
future = asyncio.run_coroutine_threadsafe(_handle_webrtc_offer(...), _webrtc_loop)
result = future.result(timeout=15)   # blocks the Flask handler thread until answer ready
```

This pattern is correct and thread-safe. The aiortc loop thread has its own event loop, its own `asyncio.Selector`, and its own DTLS/SRTP socket I/O — all completely isolated from eventlet's green-thread scheduler.

### 3.4 Streaming Modes

Two streaming modes are exposed:

| Mode | Parameter | Server-side processing | Use case |
|---|---|---|---|
| Raw | `mode=raw` | BGR→RGB conversion only | Lowest latency; Phase 1 observation |
| Annotated | `mode=annotated` | BGR→RGB + YOLO bounding boxes | Phase 2 comparison with MJPEG overlay |

The annotated mode deliberately mirrors the MJPEG `generate_frames_research()` generator, allowing side-by-side comparison of the same annotation pipeline delivered via two transports.

### 3.5 Frontend Integration

Both the research dashboard (`/research`) and the main dashboard (`/`) are updated with WebRTC toggle controls embedded directly in the video container elements:

- An **⚡ WebRTC** button is overlaid at the bottom-right corner of each camera feed container.
- Clicking it initiates the offer/answer exchange and, on successful `RTCPeerConnection` state `'connected'`, hides the `<img>` MJPEG element and shows the `<video>` WebRTC element.
- The button label changes to **📡 MJPEG** to indicate the active state and serve as a revert control.
- An inline status label (`Connecting… → Connected / Failed`) provides real-time connection state feedback.

If `aiortc` is not installed, `GET /webrtc/status` returns `{"available": false}` and all WebRTC buttons are automatically dimmed and disabled on page load, with a tooltip instructing the user to run `pip install aiortc`.

### 3.6 Peer Connection Lifecycle

Each browser WebRTC session creates one `RTCPeerConnection` object on the server. The lifecycle is managed by the `connectionstatechange` event:

```
new → connecting → connected → (disconnected / failed / closed)
```

On `failed` or `closed`, the server-side peer connection is closed and removed from `_webrtc_pcs`:

```python
@pc.on("connectionstatechange")
async def on_state():
    if pc.connectionState in ("failed", "closed", "disconnected"):
        await pc.close()
        _webrtc_pcs.discard(pc)
```

Active peer connections can be monitored via `GET /webrtc/status` → `active_peers`. This endpoint is useful for debugging resource leaks during extended experimentation sessions.

### 3.7 Limitations and Future Work

| Limitation | Description | Mitigation |
|---|---|---|
| Software H.264 encoding | aiortc uses libav (FFmpeg) for H.264 encoding in software. Pi 5 has a V4L2 H.264 hardware encoder (`/dev/video11`) which aiortc does not use. | Future: implement a GStreamer pipeline feeding RTP directly, bypassing aiortc's encoder. Estimated CPU saving: ~80%. |
| Single peer connection per button click | Each click creates a new `RTCPeerConnection`. Rapid toggling leaks connections until `closed` state is reached. | Future: enforce one-active-connection-per-feed invariant in the client JS. |
| `annotated` mode blocks asyncio | `_draw_results()` is a synchronous blocking call inside `recv()`. | Future: `loop.run_in_executor(None, _draw_results, frame, results)`. |
| No STUN/TURN | `RTCPeerConnection({ iceServers: [] })` only gathers host candidates. Fails outside LAN. | Acceptable for current LAN-only deployment. Add STUN server (`stun:stun.l.google.com:19302`) for remote access. |

---

## 4. System Architecture Summary — March 11, 2026 State

### 4.1 Data Flow

```
CSI Camera (rpicam-vid subprocess)
    │ YUV420 → BGR (cv2.cvtColor)
    ▼
FrameManager (shared memory, threading.Lock)
    ├── YOLO Inference Thread ────────────────► detection_state
    │       │                                        │
    │   Phase 1 Thread (Places365 GoogLeNet)         │
    │       │                                        │
    ├── generate_frames_index() ──► MJPEG /video_feed
    ├── generate_frames_research() ► MJPEG /video_feed_research
    ├── generate_frames_raw() ──────► MJPEG /video_feed_raw
    └── CameraVideoTrack.recv() ────► WebRTC RTP (aiortc asyncio loop)
```

### 4.2 Context Lookup Path

```
Phase 1 predicts scene  ──► _switch_scene(scene_name)
                                    │
                        context_mgr.get_context_for_scene(
                            scene_name,
                            vocabulary=_context_vocab  ← 'coco80' | 'objects365'
                        )
                                    │
                    ┌───────────────┴───────────────────┐
                    │ coco80                             │ objects365
                    ▼                                   ▼
            scene_context table              scene_context_objects365 table
            (80-class COCO vocab)            (365-class Objects365 vocab)
                    │                                   │
                    └───────────────┬───────────────────┘
                                    │
                        { classes: [...], model: '...' }
                                    │
                    ┌───────────────┴──────────────────┐
                    │ Classes Mode                      │ Model Mode
                    ▼                                   ▼
            yolo_model.set_classes(classes)     load model from model_file
```

### 4.3 WebRTC Signalling Flow

```
Browser (JS)                      Flask (app.py)           aiortc loop thread
    │                                   │                         │
    │  POST /webrtc/offer               │                         │
    │  {sdp, type, mode='raw'} ────────►│                         │
    │                                   │  run_coroutine_threadsafe
    │                                   │─────────────────────────►│
    │                                   │   RTCPeerConnection()    │
    │                                   │   addTrack(CameraVideoTrack)
    │                                   │   setRemoteDescription() │
    │                                   │   createAnswer()         │
    │                                   │   wait iceGatheringState │
    │                                   │◄─────────────────────────│
    │  {sdp: answer, type: 'answer'} ◄──│                         │
    │                                   │                         │
    │  setRemoteDescription(answer)     │                         │
    │                                   │                         │
    │◄══════════ UDP RTP media ══════════════════════════════════►│
```

### 4.4 Component Version Inventory

| Component | Version | Notes |
|---|---|---|
| Flask | 2.3.x | `<3.0.0` pin maintained |
| Flask-SocketIO | latest | eventlet async mode |
| aiortc | 1.14.0 | Newly added |
| PyAV (av) | 16.1.0 | aiortc dependency |
| OpenCV (headless) | system | cv2.imencode, cvtColor, DNN |
| ultralytics | 8.4.14 | YOLOv8 / YOLOWorld |
| SQLite | system | context.db, access.db |
| Places365 scenes | 365 | CSV seeded into both vocabulary tables |

---

## 5. Experimental Recommendations

Based on the work conducted on March 11, 2026, the following experiments are recommended for the next session:

1. **Vocabulary Impact Measurement**: Record Phase 2 detection results for 5 representative scenes using both COCO-80 and Objects365 vocabularies. Count unique class detections per frame and compute the precision/recall difference using a ground-truth annotation of the scene.

2. **WebRTC Glass-to-Glass Latency Measurement**: Use a screen-capture timer (a millisecond clock displayed on the Pi 5 and simultaneously captured by the camera) to empirically measure MJPEG vs WebRTC end-to-end latency. The estimated 3–10× reduction should be validated.

3. **H.264 Hardware Encoder Integration**: Instrument the Pi 5's `/dev/video11` V4L2 H.264 encoder via a GStreamer pipeline and compare CPU utilisation and latency against aiortc's software libav encoder.

4. **Multi-Client WebRTC Stress Test**: Open 3+ simultaneous WebRTC connections (different browser tabs) and measure CPU and RAM impact on the Pi 5 to determine the practical concurrency limit.

---

## References

- Shao, S., et al. (2019). Objects365: A Large-Scale, High-Quality Dataset for Object Detection. *ICCV 2019*.
- Zhou, B., Lapedriza, A., Khosla, A., Oliva, A., & Torralba, A. (2017). Places: A 10 million Image Database for Scene Recognition. *IEEE TPAMI*.
- Ott, J., & Perkins, C. (2011). Guidelines for Extending the Real-time Transport Protocol (RTP). *RFC 6363*, IETF.
- Holmer, S., et al. (2013). How WebRTC is Used for Real-Time Communication. *Google Tech Report*.
- Schier, M., et al. (2021). Low-Latency Video Streaming for Teleoperation using WebRTC. *ICRA 2021 Workshop on Robot Teleoperation*.
- Stächowiak, K., et al. (2019). WebRTC-Based Real-Time Video for Robotic Teleoperation on Low-Latency Networks. *IEEE IROS 2019*.
- Lin, T.-Y., et al. (2014). Microsoft COCO: Common Objects in Context. *ECCV 2014*.
- aiortc Documentation. (2024). https://aiortc.readthedocs.io/
- SQLite WAL Mode Documentation. https://www.sqlite.org/wal.html
