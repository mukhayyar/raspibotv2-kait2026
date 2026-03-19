#!/usr/bin/env python3
"""
benchmark_phase2.py  —  Measure Phase 2 latency components on this hardware.

What it measures:
  1. DB query   — context_manager.get_context_for_scene()   (SQLite + JSON parse)
  2. set_classes — yolo_model.set_classes(classes)           (CLIP text-encode + weight inject)
  3. Total       — db + set_classes combined

Run from the backend/ directory:
    python benchmark_phase2.py
    python benchmark_phase2.py --n 20 --scenes living_room kitchen office street park
"""

import argparse
import json
import os
import statistics
import sys
import time

# ─── Config ───────────────────────────────────────────────────────────────────
DEFAULT_SCENES = [
    'living_room', 'kitchen', 'bedroom', 'office', 'street',
    'park', 'restaurant', 'parking', 'hospital', 'library',
]
DEFAULT_N    = 10   # timed repetitions per scene
DEFAULT_WARM = 2    # warm-up reps (not counted)
MODEL_PATH   = os.path.join(os.path.dirname(__file__), 'models', 'yolov8s-worldv2.pt')
DB_PATH      = os.path.join(os.path.dirname(__file__), 'data', 'context.db')

# ─── Argument parsing ─────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='Benchmark Phase 2 latency')
parser.add_argument('--n',      type=int,   default=DEFAULT_N,   help='Timed reps per scene')
parser.add_argument('--warm',   type=int,   default=DEFAULT_WARM, help='Warm-up reps (not counted)')
parser.add_argument('--scenes', nargs='+',  default=DEFAULT_SCENES, help='Scene names to benchmark')
parser.add_argument('--model',  default=MODEL_PATH, help='Path to YOLOWorld .pt file')
parser.add_argument('--db',     default=DB_PATH,    help='Path to context.db')
args = parser.parse_args()

# ─── Setup ────────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
from context_manager import ContextManager

print(f"Model : {args.model}")
print(f"DB    : {args.db}")
print(f"Scenes: {args.scenes}")
print(f"Reps  : {args.warm} warm-up + {args.n} timed\n")

# Load model
try:
    from ultralytics import YOLO
    print("Loading YOLO model…", end=' ', flush=True)
    t0 = time.perf_counter()
    model = YOLO(args.model)
    print(f"done in {(time.perf_counter()-t0)*1000:.0f} ms")
except Exception as e:
    print(f"[ERROR] Could not load model: {e}")
    sys.exit(1)

ctx_mgr = ContextManager(db_path=args.db)

# ─── Benchmark ────────────────────────────────────────────────────────────────
COL  = 28
SEP  = '-' * 72

print()
print(SEP)
print(f"{'Scene':<{COL}}  {'DB (ms)':>9}  {'set_classes (ms)':>17}  {'Total (ms)':>11}")
print(SEP)

all_db     = []
all_switch = []
all_total  = []

for scene in args.scenes:
    db_times     = []
    switch_times = []

    for rep in range(args.warm + args.n):
        # ─ DB query ─
        t0 = time.perf_counter()
        ctx = ctx_mgr.get_context_for_scene(scene)
        t_db = (time.perf_counter() - t0) * 1000

        classes = ctx['classes']

        # ─ set_classes() ─
        t0 = time.perf_counter()
        model.set_classes(classes)
        t_sc = (time.perf_counter() - t0) * 1000

        if rep >= args.warm:
            db_times.append(t_db)
            switch_times.append(t_sc)

    total_times = [db_times[i] + switch_times[i] for i in range(len(db_times))]

    m_db  = statistics.mean(db_times)
    m_sc  = statistics.mean(switch_times)
    m_tot = statistics.mean(total_times)

    all_db.extend(db_times)
    all_switch.extend(switch_times)
    all_total.extend(total_times)

    n_cls = len(classes)
    print(f"{scene:<{COL}}  {m_db:>7.1f} ms  {m_sc:>14.1f} ms  {m_tot:>9.1f} ms  ({n_cls} classes)")

print(SEP)
print(f"{'OVERALL MEAN':<{COL}}  {statistics.mean(all_db):>7.1f} ms  {statistics.mean(all_switch):>14.1f} ms  {statistics.mean(all_total):>9.1f} ms")
print(f"{'OVERALL MEDIAN':<{COL}}  {statistics.median(all_db):>7.1f} ms  {statistics.median(all_switch):>14.1f} ms  {statistics.median(all_total):>9.1f} ms")
print(f"{'STDEV':<{COL}}  {statistics.stdev(all_db):>7.1f} ms  {statistics.stdev(all_switch):>14.1f} ms  {statistics.stdev(all_total):>9.1f} ms")
print(SEP)

# ─── Per-field detail for worst-case scene ────────────────────────────────────
print("\nDetailed breakdown for each timed rep (last scene):")
for i, (d, s) in enumerate(zip(db_times, switch_times)):
    bar = '█' * int(s / 10)
    print(f"  rep {i+1:02d}:  db={d:5.1f} ms  set_classes={s:7.1f} ms  total={d+s:7.1f} ms  {bar}")

print("\nDone.")
