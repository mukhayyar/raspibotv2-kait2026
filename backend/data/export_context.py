#!/usr/bin/env python3
"""Export context.db → CSV.

Usage:
    python export_context.py                  # writes context_export.csv next to this script
    python export_context.py out.csv          # custom output path
    python export_context.py --flat out.csv   # one row per class (exploded)

Modes:
    default  — one row per scene, yolo_classes as a JSON array string
    --flat   — one row per (scene, class) pair, easier for spreadsheet filtering
"""

import csv
import json
import os
import sqlite3
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(SCRIPT_DIR, 'context.db')


def export(out_path: str, flat: bool = False) -> int:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('SELECT id, scene_name, yolo_classes, model_file FROM scene_context ORDER BY scene_name')
    rows = cur.fetchall()
    conn.close()

    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        if flat:
            writer = csv.writer(f)
            writer.writerow(['id', 'scene_name', 'yolo_class', 'model_file'])
            for row in rows:
                classes = json.loads(row['yolo_classes'] or '[]')
                for cls in classes:
                    writer.writerow([row['id'], row['scene_name'], cls, row['model_file']])
        else:
            writer = csv.writer(f)
            writer.writerow(['id', 'scene_name', 'yolo_classes', 'class_count', 'model_file'])
            for row in rows:
                classes = json.loads(row['yolo_classes'] or '[]')
                writer.writerow([
                    row['id'],
                    row['scene_name'],
                    json.dumps(classes),
                    len(classes),
                    row['model_file'],
                ])

    return len(rows)


def main():
    args = sys.argv[1:]
    flat = '--flat' in args
    if flat:
        args.remove('--flat')

    out_path = args[0] if args else os.path.join(SCRIPT_DIR, 'context_export.csv')

    n = export(out_path, flat=flat)
    mode = 'flat (one row/class)' if flat else 'compact (one row/scene)'
    print(f'Exported {n} scenes [{mode}] → {out_path}')


if __name__ == '__main__':
    main()
