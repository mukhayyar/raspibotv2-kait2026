# PENS-KAIT 2026 — System Progress Report
## Research Dashboard Enhancements, Dual-Model Benchmarking, and Streaming Stability

**Project:** PENS-KAIT 2026: Adaptive Hierarchical Detection: A Two-Phase Framework for Context-Aware Object Detection on Edge Devices
**Date:** March 19, 2026
**Author:** Muhammad Tsaqif Mukhayyar, Prof. Kosuke Takano, Dr. Eng. Idris Winarno
**Supersedes:** `docs/system_progress_report_2026-03-11.md` (March 11, 2026)

---

## Abstract

This report documents the implementation work carried out on March 19, 2026, consolidating several interconnected improvements to the PENS-KAIT 2026 research dashboard. Six major contributions are described. First, the **research dashboard benchmark panels** are extended with three additional real-time metrics — detection count, average confidence, and inference jitter (σ) — providing richer per-inference statistics for both the YOLOv8s-WorldV2 and YOLOv8s base models. Second, the **scene browser** is relocated from Phase 2A to the Phase 1 panel, upgraded from a six-entry dropdown to an interactive searchable chip browser rendering all 365 Places365 scenes fetched dynamically from a new `/api/scenes` endpoint. Third, a **bilingual interface** (English / Japanese) is implemented with a persistent language toggle, covering all major UI labels via a `data-i18n` attribute system. Fourth, **CPU load is reduced** from >90% to the 70–80% range through inference resolution reduction, camera and streaming rate capping, and MJPEG quality tuning. Fifth, a **critical ONNX static-shape bug** causing the base YOLO model to silently produce only one inference is identified and fixed. Sixth, **camera feed jitter and glitch causes** are diagnosed and resolved through event-driven MJPEG delivery, single-frame encoder synchronisation, and subprocess pipe buffer enlargement.

---

## 1. Extended Benchmark Metrics

### 1.1 Motivation

The initial benchmark panel displayed only the four raw timing values from the Ultralytics speed profiler (`preprocess_ms`, `inference_ms`, `postprocess_ms`, `total_ms`). These values are necessary but insufficient for evaluating detection quality during a live scene: a model may run fast but detect nothing meaningful. Two additional per-inference statistics and one stability metric are added to both the Phase 2A (YOLOv8s-WorldV2) and Phase 2B (YOLOv8s base) panels.

### 1.2 Metrics Added

**Detection Count** (`detection_count`): the number of bounding boxes returned by the model for the current frame. Computed from `results[0].boxes` immediately after `predict()`. A value of zero indicates either that no target objects are in the scene or that the confidence threshold filters them all out.

**Average Confidence** (`avg_conf`): the mean of `results[0].boxes.conf` across all accepted detections. Reported as a percentage. A value of `—` is shown when no detections are present. This metric is useful for evaluating whether a scene-class set is appropriate for the current environment: low average confidence under a relevant scene suggests the class vocabulary may need refinement.

**Inference Jitter σ** (`bench-jitter`): the standard deviation of the last N `inference_ms` samples retained in a rolling history buffer (`_benchHistory`). Computed client-side in JavaScript as:

```js
const variance = hist.reduce((s, h) => s + (h.inference_ms - avgInf) ** 2, 0) / n;
const jitter = Math.sqrt(variance);
```

The jitter value is colour-coded: green (< 20 ms), amber (20–50 ms), red (> 50 ms). High jitter on a Raspberry Pi 5 indicates GIL contention or thermal throttling rather than a model-level issue. At least two samples are required before jitter is displayed.

### 1.3 Backend Changes

Both `inference_thread` (YOLOv8s-WorldV2) and `base_inference_thread` (YOLOv8s) now include `detection_count` and `avg_conf` in the `inference_speed` Socket.IO emit payload:

```python
_boxes = results[0].boxes
_det_n = int(len(_boxes)) if _boxes is not None else 0
_avg_c = round(float(_boxes.conf.mean().item()) if _det_n > 0 else 0.0, 3)
socketio.emit('inference_speed', {
    'model_key':       'worldv2',   # or 'base'
    'detection_count': _det_n,
    'avg_conf':        _avg_c,
    ...
})
```

---

## 2. Scene Browser Relocation and Full Places365 Integration

### 2.1 Previous Design Problem

In the original dashboard, Phase 2A contained a `<select>` element with six hardcoded scene names (`parking_lot`, `kitchen`, `classroom`, `gym`, `office`, `corridor`). This was a placeholder that did not reflect the 365-scene database and required manual code editing to change the available options. Researchers could not explore scene-class mappings interactively.

### 2.2 New Architecture

The scene selector is removed from Phase 2A entirely. A new **scene browser** component is inserted into the Phase 1 panel (right column), positioned between the transition mode selector and the Phase 1 history table. Its data source is a new public HTTP endpoint `/api/scenes`:

```python
@app.route('/api/scenes')
def api_scenes():
    vocab = request.args.get('vocab', 'coco80')
    scenes = context_mgr.get_all_scenes(vocabulary=vocab)
    return jsonify([{'name': s['name'], 'class_count': len(s['classes'])} for s in scenes])
```

The endpoint requires no authentication, allowing the research page to call it without a Socket.IO session. On page load, `_loadSceneBrowser()` fetches all 365 scenes and renders them as clickable **chip elements** (`.scene-chip` CSS class). An inline search input (`<input id="scene-search">`) filters chips in real time via `filterScenes()`. The active scene chip is highlighted with a blue border and bold weight.

Selecting a chip calls `setSceneFromBrowser(name)`, which emits `socket.emit('set_scene', { scene: name })` and sets `currentMode = 'manual'`, preventing the Phase 1 auto-switch from overriding the manual selection.

### 2.3 Placement Rationale

Phase 1 is responsible for scene identification. The scene override control belongs logically in the Phase 1 panel rather than Phase 2A because it directly affects Phase 1's output: setting a scene manually bypasses Phase 1 inference and forces a specific context for Phase 2. Placing the selector in Phase 2A implied that the scene was a Phase 2 parameter, which is architecturally incorrect.

---

## 3. Bilingual Interface (EN / JP)

### 3.1 Implementation

A language toggle button (`🌐 日本語` / `🌐 English`) is added to the page header. Clicking it calls `toggleLang()`, which calls `applyLang(lang)`. The `applyLang` function iterates over all elements with `data-i18n` attributes and replaces their text content with the corresponding translation from the `_I18N` dictionary. The selected language is persisted to `localStorage` under the key `pens_lang` and re-applied on page load.

The translation dictionary contains 40 key–value pairs covering all structural UI labels in both the Phase 1 and Phase 2 panels, the benchmark sections, alert rules, and comparison panels. Japanese translations use standard JIS technical terminology for the AI/ML domain.

### 3.2 Scope Bug and Fix

All i18n functions (`toggleLang`, `applyLang`), as well as the scene browser functions (`filterScenes`, `setSceneFromBrowser`), were inadvertently placed inside the WebRTC IIFE (`(function(){ ... })()`). Functions defined inside an IIFE are local to that closure and are not accessible from `window` scope. HTML `onclick="..."` attributes resolve function names against `window`, so all button and chip click handlers were silently failing.

**Fix:** Each function called from an HTML `onclick` or `oninput` attribute is explicitly assigned to `window` after its definition:

```js
window.toggleLang        = toggleLang;
window.filterScenes      = filterScenes;
window.setSceneFromBrowser = setSceneFromBrowser;
```

This resolves the scope issue without restructuring the IIFE or moving code to a different script block.

---

## 4. CPU Load Reduction

### 4.1 Problem

With two concurrent YOLO inference threads, Phase 1 (Places365 GoogLeNet), MJPEG encoding, and multiple HTTP streaming generators all active simultaneously on the Raspberry Pi 5, total CPU utilisation exceeded 90%, causing thermal throttling and degraded inference timing stability.

### 4.2 Changes Applied

| Parameter | Before | After | Rationale |
|---|---|---|---|
| `_INFER_IMGSZ` | 192 px | 160 px | YOLO inference complexity scales with image area; 160²/192² ≈ 69% of prior compute |
| Camera framerate (`LibCameraCapture`) | 60 FPS | 24 FPS | Eliminates unnecessary camera frames that inference threads cannot process |
| USB camera `CAP_PROP_FPS` | unset | 24 | Aligns USB path with CSI cap |
| `_CAM_INTERVAL` hard-cap | none | 1/24 s | Prevents burst frame delivery after GIL pauses |
| `_FRAME_INTERVAL` (MJPEG streaming) | 1/30 s | 1/24 s | Aligns HTTP delivery rate with source frame rate |
| `_MJPEG_QUALITY` | 65 | 55 | JPEG encoding CPU scales with quality; 55 is visually adequate for research monitoring |

The combined effect reduces expected CPU from >90% to approximately 70–80%, leaving headroom for burst inference activity without triggering thermal throttling.

---

## 5. ONNX Static-Shape Bug in Base YOLO Model

### 5.1 Symptom

After the `_INFER_IMGSZ` change from 192 to 160, the base inference thread (`base_inference_thread`) produced exactly one valid result set and then silently stopped emitting detections. The `inference_speed` Socket.IO event was not emitted after the first frame, and the Phase 2B video feed showed a static annotated frame rather than a live stream.

### 5.2 Root Cause

`_load_base_model()` attempted to load `yolov8s.onnx` before falling back to `yolov8s.pt`. The ONNX file had been exported previously with `imgsz=192, dynamic=False`, creating a **statically shaped** computation graph. When `predict(frame, imgsz=160)` was called, the ONNX runtime accepted the call on the first invocation (returning correct results) but returned an empty or falsy result object on all subsequent calls due to the input shape mismatch. The guard:

```python
if not results:
    continue
```

caused the thread to loop indefinitely without emitting anything, appearing externally as if the model had stopped after one frame.

### 5.3 Fix

Two changes are made:

1. **Delete the stale ONNX file** (`backend/models/yolov8s.onnx`). Keeping it would allow the bug to recur on the next server restart.

2. **Rewrite `_load_base_model()`** to always load the `.pt` checkpoint, removing the ONNX preference path and the background ONNX export routine entirely:

```python
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
```

The PyTorch `.pt` checkpoint uses dynamic shapes internally and correctly handles any `imgsz` value passed to `predict()` at runtime. The ONNX optimisation (faster on OnnxRuntime/ARM) remains available for the WorldV2 model, which does not share this constraint.

A redundant thread-local `threading.Lock()` (`_base_lock`) that provided no mutual exclusion benefit (it was used by only one thread) is also removed.

---

## 6. Camera Feed Jitter and Glitch Resolution

### 6.1 Diagnosed Causes

Four distinct causes of camera feed irregularity are identified:

**Cause 1 — Polling-based MJPEG delivery (primary jitter source).** The `_stream_from_cache` function previously looped with `time.sleep(1/24)` independently of the MJPEG encoder thread's output rate. Because these are two separate timing loops with no synchronisation, they drift relative to each other, producing irregular inter-frame gaps at the HTTP layer. The browser's MJPEG decoder, which has no frame timing metadata, displays frames as they arrive; uneven arrival causes visible stutter.

**Cause 2 — Duplicate frame sends.** The streamer did not track whether the JPEG cache had been updated since the last yield. If the encoder was delayed (e.g., by GIL contention during YOLO post-processing), the same JPEG bytes were yielded twice in succession, appearing as a momentary freeze.

**Cause 3 — Temporal desync between feed variants.** `mjpeg_encoder_thread` drew the WorldV2 annotated variant on the `frame` copy received from `frame_manager.wait_for_new()`, then called `frame_manager.get()` a second time to obtain a "clean" frame for the raw and base variants. Between these two calls, the camera capture thread might have written a new frame, causing the three video feeds to be drawn from different camera timestamps. Detection boxes on the annotated feed were thus positioned relative to a frame that did not match the raw feed shown alongside it.

**Cause 4 — rpicam-vid subprocess pipe stalls.** The OS pipe buffer between the `rpicam-vid` subprocess and the Python read loop is 64 KB by default. A 640×640 YUV420 frame occupies 614,400 bytes, meaning the buffer can absorb only approximately 4 ms of data before the subprocess blocks. Under GIL pressure from concurrent YOLO threads, the Python capture thread could be paused for 10–50 ms, causing the subprocess to stall and then deliver a burst of frame data when unblocked. This burst creates irregular frame delivery to downstream threads.

### 6.2 Fixes Applied

**Fix 1 — Event-driven MJPEG delivery.** The `_jpeg_cache_lock` is replaced with a `threading.Condition` (`_jpeg_cache_cond`). A version counter (`_jpeg_cache_version`) is incremented each time the encoder writes a new set of JPEG variants. The `_stream_from_cache` function blocks on `_jpeg_cache_cond.wait_for(lambda: _jpeg_cache_version != last_version, timeout=1.0)` instead of sleeping. This ensures each HTTP generator wakes exactly when new frame data is ready — no sooner, no later:

```python
with _jpeg_cache_cond:
    _jpeg_cache_cond.wait_for(
        lambda: _jpeg_cache_version != last_version,
        timeout=1.0
    )
    new_version = _jpeg_cache_version
    jpeg_bytes  = globals()[cache_attr]
```

**Fix 2 — Deduplication by version.** Each streamer tracks `last_version`. A frame is only yielded when `new_version != last_version`, making duplicate sends structurally impossible.

**Fix 3 — Single-frame encoder.** `mjpeg_encoder_thread` now makes two explicit `.copy()` calls on the frame received from `wait_for_new()` and uses these copies for the raw and base variants. The second `frame_manager.get()` call is eliminated. All three JPEG variants are guaranteed to be drawn from the same camera frame:

```python
ann_frame  = frame          # already a copy from wait_for_new
raw_frame  = frame.copy()
base_frame = frame.copy()
```

**Fix 4 — Enlarged subprocess pipe buffer.** The `bufsize` argument to `subprocess.Popen` for `rpicam-vid` is set to 4× the YUV420 frame size (~2.4 MB), providing approximately 165 ms of buffer capacity at 24 FPS. This absorbs typical GIL pauses without stalling the subprocess:

```python
bufsize=int(width * height * 1.5 * 4),  # 4-frame buffer
```

---

## 7. Base YOLO Detected Objects Panel

Prior to this session, `base_inference_thread` populated `_base_detection_results` (used to draw bounding boxes on the `/video_feed_base` stream) but did not broadcast detections to the browser as structured data. The Phase 2B panel therefore showed no text list of detected objects, unlike Phase 2A which displayed a `detected-objects` div updated via the `detection_results` Socket.IO event.

**Change:** After parsing detections into `new_base_results`, the thread now emits:

```python
socketio.emit('base_detection_results', new_base_results)
```

A corresponding `info-box` is added to the Phase 2B panel HTML:

```html
<div class="info-box" style="margin-top:12px;">
    <div data-i18n="detected-lbl" style="...">Detected Objects:</div>
    <div id="base-detected-objects" style="color:#a78bfa; ...">-</div>
</div>
```

And the Socket.IO handler in the research page JavaScript is updated:

```js
function _renderDetections(results, el) {
    if (!results || results.length === 0) { el.innerText = 'None'; return; }
    const counts = {};
    results.forEach(d => { counts[d.class] = (counts[d.class] || 0) + 1; });
    el.innerText = Object.entries(counts).map(([k, v]) => `${k} (${v})`).join(', ');
}

socket.on('detection_results',      (r) => _renderDetections(r, elObjects));
socket.on('base_detection_results', (r) => _renderDetections(r, elBaseObjects));
```

The label reuses the existing `detected-lbl` i18n key and therefore translates automatically in both English and Japanese without additional dictionary entries.

---

## 8. Summary of Files Modified

| File | Nature of Change |
|---|---|
| `backend/app.py` | Extended `inference_speed` payload; new `/api/scenes` endpoint; `_load_base_model()` rewritten (.pt only); `_CAM_INTERVAL`, `_INFER_IMGSZ`, MJPEG quality tuned; `LibCameraCapture` framerate and pipe buffer updated; `_jpeg_cache_lock` replaced with `_jpeg_cache_cond` + `_jpeg_cache_version`; `_stream_from_cache` rewritten as event-driven; `mjpeg_encoder_thread` single-frame sync fix; `base_detection_results` Socket.IO emit added |
| `backend/models/yolov8s.onnx` | **Deleted** — stale static-shape export at imgsz=192 |
| `backend/templates/research.html` | Six-option scene dropdown removed from Phase 2A; full 365-scene chip browser added to Phase 1; benchmark panels extended (detection count, avg conf, jitter σ); language toggle button added; 40-key EN/JP i18n dictionary and `applyLang`/`toggleLang` logic added; `base-detected-objects` panel added to Phase 2B; `window.*` exports added to escape WebRTC IIFE scope |

---

## 9. Known Limitations and Future Work

- **YOLOWorld ONNX optimisation**: The WorldV2 model still loads from ONNX (`yolov8s-worldv2.onnx`). This file should be verified to have been exported at the current `_INFER_IMGSZ=160`. If it was also exported at 192, the same static-shape bug could potentially manifest under certain runtime conditions. Recommended action: delete and re-export, or switch WorldV2 to `.pt` as well.

- **GIL contention**: With two YOLO threads and Phase 1 all running Python-side pre/post-processing, the GIL remains a bottleneck. Migrating inference to a subprocess or using `multiprocessing` would eliminate GIL contention entirely and further improve streaming stability.

- **i18n coverage for dynamic content**: Scene chip labels, Phase 1 prediction results, and dynamically generated alert rule text are not translated. These require runtime translation logic rather than static dictionary lookup.

- **Base model detected objects in alerts**: The alert system currently monitors only WorldV2 `detection_results`. Extending alert rules to optionally target `base_detection_results` would allow comparison-driven alerting experiments.
