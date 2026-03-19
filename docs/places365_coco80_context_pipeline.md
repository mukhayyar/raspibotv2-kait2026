# Context-Adaptive Object Detection Pipeline
## Using Places365 Scene Recognition to Drive COCO-80 Class Selection

**Project:** PENS-KAIT 2026: Adaptive Hierarchical Detection: A Two-Phase Framework for Context-Aware in Edge Device
**Date:** March 9, 2026
**Author:** Muhammad Tsaqif Mukhayyar, Prof. Kosuke Takano, Dr. Eng. Idris Winarno

---

## Abstract

This document describes the two-phase context-adaptive detection pipeline implemented in the Yahboom RaspBotV2 robot control system. Phase 1 uses a Places365-pretrained GoogLeNet model to recognise the current scene. Phase 2 uses that scene label to dynamically select a relevant subset of COCO-80 detection classes for YOLOv8s-WorldV2, reducing false positives and improving relevance of detections. The mapping between scenes and classes is stored in a SQLite database (`context.db`) with 365 entries. The system also supports pre-generating per-scene frozen YOLO models to eliminate the run-time cost of CLIP text re-encoding. A web interface (`/manage-context`) allows full CRUD management of the database without code changes.

---

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Camera Frame                           │
│                    (CSI / USB, 640×480)                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
          ┌──────────────▼──────────────┐
          │       Inference Thread      │
          │  (runs on every frame)      │
          └──────┬───────────┬──────────┘
                 │           │
    ┌────────────▼───┐  ┌────▼─────────────────┐
    │    Phase 1     │  │       Phase 2          │
    │  Scene Reco.   │  │  Object Detection      │
    │  Places365     │  │  YOLOv8s-WorldV2       │
    │  GoogLeNet     │  │  (COCO-80 subset)      │
    └────────────────┘  └────────────────────────┘
           │                     ▲
           │  scene label        │  context switch
           └──── stability ──────┘
                 tracker         │
                           ┌─────▼──────┐
                           │ context.db │
                           │ SQLite     │
                           │ 365 scenes │
                           └────────────┘
```

---

## 2. Phase 1 — Places365 Scene Recognition

### 2.1 Model

Phase 1 uses a **GoogLeNet (Inception v1)** convolutional neural network pretrained on the **Places365 dataset** (B. Zhou et al., 2018). The model is loaded via OpenCV DNN (`cv2.dnn`) from a pre-converted Caffe `.caffemodel` / `.prototxt` pair, making it deployable on CPU without a GPU.

- Input: single BGR frame resized to **224 × 224**
- Output: 365-dimensional softmax probability vector
- Inference rate: once per second (throttled to avoid CPU contention with Phase 2)

### 2.2 Inference and Softmax

The raw output of the network is a logit vector $\mathbf{z} \in \mathbb{R}^{365}$, where each element corresponds to one Places365 scene class. The predicted probability for scene $s_i$ is:

$$P(s_i \mid \mathbf{x}) = \frac{e^{z_i}}{\displaystyle\sum_{j=1}^{365} e^{z_j}}$$

The predicted scene at time step $t$ is the argmax:

$$\hat{s}_t = \arg\max_{i \in \{1,\ldots,365\}} P(s_i \mid \mathbf{x}_t)$$

### 2.3 Scene Stability Tracking

A single frame prediction is too noisy to trigger an expensive context switch. A **scene stability tracker** (debounce mechanism) requires the same scene to appear $N = 3$ consecutive times before triggering Phase 2:

$$\text{switch}(t) = \mathbb{1}\!\left[\forall\, k \in \{0,\ldots,N-1\} : \hat{s}_{t-k} = s^*\right] \;\wedge\; \left(s^* \neq s_{\text{current}}\right)$$

where $s^*$ is the candidate scene and $s_{\text{current}}$ is the currently active scene. The stability threshold $N$ is configurable (`_SCENE_STABILITY_THRESHOLD = 3` in `app.py`).

**State variables:**

| Variable | Type | Description |
|---|---|---|
| `_candidate_scene` | `str` | Scene currently being evaluated |
| `_candidate_count` | `int` | Consecutive match count for candidate |
| `_current_scene` | `str` | Scene currently active in Phase 2 |

When a switch is triggered, `_candidate_count` resets to 0 and a background thread executes `_switch_scene(s*)`.

---

## 3. Phase 2 — Context-Adaptive Object Detection

### 3.1 YOLOv8s-WorldV2

Phase 2 uses **YOLOv8s-WorldV2** (Ultralytics, 2024), a variant of YOLOv8-small that replaces the fixed classification head with an **open-vocabulary CLIP-based detection head**. This allows the set of detectable classes to be changed at runtime without reloading the full model weights.

Standard YOLO detection score for a bounding box $b$ predicting class $c$:

$$\text{score}(b, c) = P(\text{obj} \mid b) \cdot \text{IoU}(b,\, b^*_{\text{gt}}) \cdot P(c \mid \text{obj}, b)$$

In YOLOWorld, $P(c \mid \text{obj}, b)$ is replaced by a similarity score between the visual region embedding $\mathbf{v}_b$ and the CLIP text embedding $\mathbf{e}_c$:

$$P(c \mid b) = \frac{\exp\!\left(\mathbf{v}_b \cdot \mathbf{e}_c \,/\, \tau\right)}{\displaystyle\sum_{c' \in \mathcal{C}_s} \exp\!\left(\mathbf{v}_b \cdot \mathbf{e}_{c'} \,/\, \tau\right)}$$

where $\tau$ is a learned temperature parameter and $\mathcal{C}_s$ is the scene-specific class set.

### 3.2 CLIP Text Embedding for Class Vocabulary

The CLIP text encoder maps a class name string to a unit vector in the joint vision-language embedding space:

$$\mathbf{e}_c = \frac{\text{CLIP}_\text{text}\!\left(\texttt{"a photo of a } c\texttt{"}\right)}{\left\|\text{CLIP}_\text{text}\!\left(\texttt{"a photo of a } c\texttt{"}\right)\right\|_2}, \quad c \in \mathcal{C}_s$$

When `model.set_classes(C_s)` is called, the encoder runs for all $|\mathcal{C}_s|$ class names. The resulting embedding matrix is:

$$\mathbf{E}_s = \left[\mathbf{e}_{c_1} \;\Big|\; \mathbf{e}_{c_2} \;\Big|\; \cdots \;\Big|\; \mathbf{e}_{c_n}\right] \in \mathbb{R}^{d \times n}$$

This matrix is injected into the YOLO detection head, replacing the previous class vocabulary. **This re-encoding step is the bottleneck** — it takes 3–8 seconds on Raspberry Pi 5 (CPU-only) due to the CLIP transformer forward pass.

### 3.3 Context DB Lookup

When a scene switch is triggered, the system queries the database for the class list:

$$\mathcal{C}_s = \text{DB\_lookup}(s) = \left\{c \in \mathcal{C}_{\text{COCO-80}} \;\Big|\; (s, c) \in \text{scene\_context}\right\}$$

The lookup involves: (1) exact match on `scene_name`, (2) normalised name fallback, (3) fuzzy substring match. This entire operation takes **< 2 ms** on Pi 5 (SQLite in-process).

---

## 4. Context Database — `context.db`

### 4.1 Schema

The database contains a single table `scene_context`:

```sql
CREATE TABLE scene_context (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_name  TEXT UNIQUE NOT NULL,
    yolo_classes TEXT NOT NULL,   -- JSON array of strings, e.g. ["person","chair","laptop"]
    model_file  TEXT DEFAULT 'yolov8s-worldv2.pt'
);
```

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Auto-incrementing primary key |
| `scene_name` | TEXT | Places365 simple scene name (e.g. `living_room`, `street`) |
| `yolo_classes` | TEXT | JSON array of COCO-80 class names relevant to this scene |
| `model_file` | TEXT | Model filename to load in *model mode* (default: shared WorldV2) |

### 4.2 Population Strategy

The database was seeded from the **Places365 scene hierarchy CSV** (`Scene hierarchy - Places365.csv`). This CSV contains 365 rows, one per scene, with:

- **Column 0:** scene path (e.g. `/a/airfield`, `/l/living_room`)
- **Columns 1–3:** binary indoor/outdoor flags
- **Columns 4–19:** 16 Level-2 category binary flags

Scene names are extracted by stripping the path prefix and joining sub-path components with underscores:

```
'/l/living_room'        → 'living_room'
'/a/apartment_building/outdoor' → 'apartment_building_outdoor'
```

### 4.3 Class Assignment Algorithm

Class assignment is a two-stage process validated against the COCO-80 vocabulary $\mathcal{C}_{\text{COCO-80}}$.

**Stage 1 — Category-level classes.** Each of the 16 Level-2 category flags maps to a fixed list of COCO-80 classes likely to appear in that environment type. For example:

| Category index | Category name | Example classes assigned |
|---|---|---|
| 0 | Shopping and dining | `chair`, `dining table`, `bottle`, `cup`, `wine glass` |
| 1 | Workplace | `chair`, `laptop`, `keyboard`, `mouse`, `cell phone` |
| 2 | Home or hotel | `chair`, `couch`, `bed`, `tv`, `remote`, `clock` |
| 10 | Transportation (roads) | `car`, `bus`, `truck`, `traffic light`, `stop sign` |
| 14 | Houses, farms | `horse`, `sheep`, `cow`, `dog`, `cat`, `bird` |

**Stage 2 — Keyword-level classes.** The scene name is split into individual words (on `_` separators), and each word is matched against a keyword → class dictionary with 100+ entries. For example:

| Keyword | Classes added |
|---|---|
| `kitchen` | `microwave`, `oven`, `toaster`, `sink`, `refrigerator`, `bowl` |
| `bedroom` | `bed`, `clock`, `book`, `cell phone`, `teddy bear`, `laptop` |
| `street` | `car`, `bus`, `truck`, `bicycle`, `motorcycle`, `traffic light` |
| `park` | `bench`, `bird`, `dog`, `bicycle`, `frisbee`, `kite` |

The final class set for scene $s$ is:

$$\mathcal{C}_s = \left(\bigcup_{i \in \text{flags}(s)} \mathcal{K}_i \;\cup\; \bigcup_{w \in \text{words}(s)} \mathcal{W}_w \;\cup\; \{\texttt{person}\}\right) \;\cap\; \mathcal{C}_{\text{COCO-80}}$$

where $\mathcal{K}_i$ are the category-level classes for flag $i$, $\mathcal{W}_w$ are keyword-level classes for word $w$, and `person` is always included as a baseline.

**Result:** 365 scenes, avg. **11.8 classes/scene**, min. 3, max. 18, all validated against COCO-80.

---

## 5. Context Management Interface (`/manage-context`)

### 5.1 Overview

`/manage-context` is a password-protected Flask route that provides a full CRUD interface for the `scene_context` table. It is the primary tool for curating the scene → class mappings without touching code or the database file directly.

Access is controlled via Flask session (`session['ctx_authed']`). The password is read from the `ADMIN_PASSWORD` environment variable, shared with the Socket.IO authentication layer.

### 5.2 REST API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/manage-context` | Renders the management page (login overlay if not authenticated) |
| `POST` | `/manage-context/login` | Authenticates with `{ password }`, sets session cookie |
| `POST` | `/manage-context/logout` | Clears session |
| `GET` | `/api/context/scenes?q=<query>` | Lists all scenes (with optional search filter) |
| `POST` | `/api/context/scenes` | Creates a new scene entry |
| `PUT` | `/api/context/scenes/<id>` | Updates `yolo_classes` and/or `model_file` for a scene |
| `DELETE` | `/api/context/scenes/<id>` | Deletes a scene entry |
| `GET` | `/api/context/models` | Lists `.pt` files available in `backend/models/` |

### 5.3 Frontend Features

The management page (`manage_context.html`) provides:

- **Search bar** with 250 ms debounce — filters scenes in real-time, shows match count
- **Tag editor** — YOLO classes displayed as removable chips; press Enter or comma to add a new class
- **COCO-80 quick-add buttons** — all 80 COCO classes shown as clickable pills; highlighted when the class is already in the current scene's list
- **Model file dropdown** — populated from `/api/context/models`, selects which frozen `.pt` file Phase 2 loads for this scene in *model mode*
- **Add / Edit / Delete** scene operations

---

## 6. Phase 2 Mode Selection

The system supports two modes for Phase 2, togglable from the research page without restarting the server.

### 6.1 Classes Mode (default)

In *classes mode*, a single `yolov8s-worldv2.pt` model is kept in memory. On every scene switch, `set_classes()` is called with the new class list from the DB:

```
scene switch triggered
    │
    ├─ DB lookup → C_s    (~1 ms)
    └─ set_classes(C_s)   (~3–8 s on Pi 5 CPU)
```

**Advantages:** Only one model loaded into RAM (~50 MB). Works immediately with the base model, no pre-generation step needed.
**Disadvantages:** 3–8 second freeze per scene switch (CLIP encoding on CPU).

### 6.2 Model Mode

In *model mode*, a separate frozen `.pt` file is loaded per scene. The `model_file` column in `context.db` specifies which file to load. `set_classes()` is never called at runtime.

```
scene switch triggered
    │
    ├─ DB lookup → model_file    (~1 ms)
    └─ YOLO(model_file)          (~300–600 ms on Pi 5)
```

**Advantages:** ~10× faster scene switch. CLIP encoding happened offline at model generation time.
**Disadvantages:** Requires pre-generating 365 × ~50 MB model files; ~18 GB total disk.

### 6.3 Frozen Model Generation

A frozen model for scene $s$ is defined as:

$$\mathcal{M}_s(\mathbf{x}) \;\equiv\; \mathcal{M}\!\left(\mathbf{x};\; \mathbf{E}_s\right)$$

where $\mathcal{M}$ is the base YOLOWorld model and $\mathbf{E}_s$ is the embedding matrix for scene $s$'s class vocabulary (§3.2). The `.save()` call serialises $\mathbf{E}_s$ into the PyTorch checkpoint alongside the backbone and detection head weights, so loading the file directly provides the frozen vocabulary without any CLIP call.

**Generation procedure** (Colab notebook `generate_frozen_models_coco80.ipynb`):

```python
for scene_name, classes in SCENES.items():
    model = YOLO('yolov8s-worldv2.pt')   # reload base weights
    model.set_classes(classes)            # run CLIP: bakes E_s into weights
    model.save(f'{scene_name}.pt')        # serialise frozen model
```

On a T4 GPU (Colab), `set_classes()` takes ~50–200 ms per scene, making the full 365-scene generation feasible in ~5 minutes.

### 6.4 Latency Comparison

Measured on **Raspberry Pi 5** (ARM Cortex-A76, 4 cores, CPU-only):

| Component | Classes Mode | Model Mode |
|---|---|---|
| DB query | ~1 ms | ~1 ms |
| CLIP / model load | **3,000–8,000 ms** | **300–600 ms** |
| Total switch latency | **3–8 s** | **0.3–0.6 s** |
| RAM (one model) | ~50 MB | ~50 MB |
| Disk (all 365 scenes) | 50 MB | ~18 GB |

---

## 7. Detection Alert Rules

### 7.1 Rule Structure

Each alert rule defines:
- **`class_name`** — COCO-80 class to watch for
- **`action`** — `led_color`, `buzzer_beep`, or `buzzer_pattern`
- **`threshold`** — minimum detection confidence
- **`trigger_frames`** $T_r = 2$ — consecutive frames with the class present before activating
- **`clear_frames`** $T_c = 3$ — consecutive frames with the class absent before deactivating

### 7.2 Hysteresis Function

Let $d_t(c) = \mathbb{1}[\exists\, b_t : \text{class}(b_t) = c \;\wedge\; \text{conf}(b_t) \geq \theta]$ be the indicator that class $c$ is detected with confidence $\geq \theta$ at frame $t$.

The alert state evolves as:

$$\text{active}_{t}(r) = \begin{cases}
1 & \text{if } \text{active}_{t-1}(r) = 0 \;\wedge\; \displaystyle\sum_{k=0}^{T_r-1} d_{t-k}(c_r) = T_r \\
0 & \text{if } \text{active}_{t-1}(r) = 1 \;\wedge\; \displaystyle\sum_{k=0}^{T_c-1} d_{t-k}(c_r) = 0 \\
\text{active}_{t-1}(r) & \text{otherwise}
\end{cases}$$

This two-sided hysteresis prevents hardware chatter from momentary false positives or brief disappearances.

---

## 8. Data Flow Summary

```
Frame (t)
  │
  ├─[YOLO, every frame]─────────────────────────────────────────────────┐
  │   YOLOWorld predict(frame, classes=C_s_current)                      │
  │   → detections {class, conf, bbox}                                   │
  │   → alert rule evaluation (hysteresis)                               │
  │   → emit detection_results (WebSocket)                               │
  │                                                                      │
  └─[Phase 1, once/second]──────────────────────────────────────────┐   │
      GoogLeNet predict(frame_resized_224)                            │   │
      → P(s_i | x) for i=1..365                                      │   │
      → top-1 scene label s_hat                                       │   │
      → emit phase1_result (WebSocket)                                │   │
      → stability tracker:                                            │   │
            candidate_count++ if s_hat == candidate_scene             │   │
            if candidate_count >= 3 and s_hat != current_scene:       │   │
                spawn _switch_scene(s_hat) thread ─────────────────┐  │   │
                                                                    │  │   │
                                                        ┌───────────▼──▼───▼──┐
                                                        │  _switch_scene(s)   │
                                                        │  1. DB lookup → C_s │
                                                        │  2a. set_classes(Cs)│
                                                        │   or               │
                                                        │  2b. YOLO(model.pt) │
                                                        │  3. emit context_   │
                                                        │     switched + timing│
                                                        └────────────────────┘
```

---

## 9. File Reference

| File | Role |
|---|---|
| `backend/app.py` | Main Flask + Socket.IO server; Phase 1/2 inference thread; `_switch_scene()` |
| `backend/context_manager.py` | `ContextManager` class; DB init, seeding, `get_context_for_scene()` |
| `backend/data/context.db` | SQLite database; 365 scene → COCO-80 class mappings |
| `backend/data/context_new.db` | Alternative DB with Objects365 vocabulary (~250 classes/scene) |
| `backend/data/export_context.py` | Exports `context.db` to CSV (compact or flat/exploded) |
| `backend/models/yolov8s-worldv2.pt` | Base YOLOWorld model file |
| `backend/models/yolo26n.pt` | Lightweight fixed-class YOLO v11/26 nano (no set_classes support) |
| `backend/templates/research.html` | Research experiment page; Phase 2 mode toggle, timing panel, alert rules |
| `backend/templates/manage_context.html` | Context database management UI |
| `notebooks/generate_frozen_models_coco80.ipynb` | Generates 365 frozen COCO-80 scene models (Colab) |
| `notebooks/yolov8s_world_objects365_finetune.ipynb` | Fine-tunes YOLOWorld on Objects365 dataset (Colab) |
| `notebooks/generate_scene_models.ipynb` | Generates frozen models from fine-tuned checkpoint + benchmarks |
| `backend/benchmark_phase2.py` | Measures DB query and `set_classes()` latency on current hardware |

---

## 10. References

1. B. Zhou, A. Lapedriza, A. Khosla, A. Oliva, and A. Torralba, "Places: A 10 million image database for scene recognition," *IEEE Transactions on Pattern Analysis and Machine Intelligence*, vol. 40, no. 6, pp. 1452–1464, 2018.

2. A. Wang, H. Chen, L. Liu, K. Chen, Z. Lin, J. Han, and G. Ding, "YOLOv10: Real-time end-to-end object detection," *arXiv:2405.14458*, 2024.

3. T.-Y. Lin, M. Maire, S. Belongie, J. Hays, P. Perona, D. Ramanan, P. Dollár, and C. L. Zitnick, "Microsoft COCO: Common objects in context," in *ECCV*, 2014, pp. 740–755.

4. A. Radford, J. W. Kim, C. Hallacy, A. Ramesh, G. Goh, S. Agarwal, G. Sastry, A. Askell, P. Mishkin, J. Clark, G. Krueger, and I. Sutskever, "Learning transferable visual models from natural language supervision," in *ICML*, 2021.

5. Ultralytics, "YOLOv8: A new state-of-the-art AI architecture," GitHub repository, 2023. [Online]. Available: https://github.com/ultralytics/ultralytics

6. J. Deng, W. Dong, R. Socher, L.-J. Li, K. Li, and L. Fei-Fei, "ImageNet: A large-scale hierarchical image database," in *CVPR*, 2009, pp. 248–255.
