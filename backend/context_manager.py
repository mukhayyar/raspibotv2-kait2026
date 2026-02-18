import sqlite3
import os
import csv
import json

class ContextManager:
    def __init__(self, db_path=None, csv_path=None):
        if db_path is None:
            # Default to backend/data/context.db
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.db_path = os.path.join(base_dir, 'data', 'context.db')
        else:
            self.db_path = db_path

        if csv_path is None:
             base_dir = os.path.dirname(os.path.abspath(__file__))
             self.csv_path = os.path.join(base_dir, 'data', 'Scene hierarchy - Places365.csv')
        else:
            self.csv_path = csv_path
            
        self._init_db()

    def _init_db(self):
        """Initialize the database and seed it if empty."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scene_context (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scene_name TEXT UNIQUE NOT NULL,
                    yolo_classes TEXT NOT NULL, -- JSON list of strings
                    model_file TEXT DEFAULT 'yolov8s-worldv2.pt'
                )
            ''')
            
            # Migration: Check if model_file exists (for existing DBs)
            cursor.execute("PRAGMA table_info(scene_context)")
            columns = [info[1] for info in cursor.fetchall()]
            if 'model_file' not in columns:
                print("[ContextManager] Migrating DB: Adding model_file column...")
                cursor.execute("ALTER TABLE scene_context ADD COLUMN model_file TEXT DEFAULT 'yolov8s-worldv2.pt'")

            conn.commit()
            
            # Check if seeded
            cursor.execute('SELECT COUNT(*) FROM scene_context')
            count = cursor.fetchone()[0]
            if count == 0:
                self._seed_db(conn)

    def _seed_db(self, conn):
        print(f"[ContextManager] Seeding database from {self.csv_path}...")
        cursor = conn.cursor()
        
        # COCO / YOLOv8s-worldv2 classes provided by user
        YOLO_CLASSES = [
            'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat', 'traffic light',
            'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat', 'dog', 'horse', 'sheep', 'cow',
            'elephant', 'bear', 'zebra', 'giraffe', 'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee',
            'skis', 'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard',
            'tennis racket', 'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple',
            'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch',
            'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse', 'remote', 'keyboard',
            'cell phone', 'microwave', 'oven', 'toaster', 'sink', 'refrigerator', 'book', 'clock', 'vase',
            'scissors', 'teddy bear', 'hair drier', 'toothbrush'
        ]

        # Heuristic mapping function
        def get_classes(scene):
            scene = scene.lower().replace('/', '_')
            base = ['person'] # Person is almost always relevant
            
            # Transport / Outdoors
            if any(x in scene for x in ['street', 'road', 'highway', 'parking', 'crosswalk', 'driveway']):
                base.extend(['car', 'bus', 'truck', 'bicycle', 'motorcycle', 'traffic light', 'stop sign'])
            if 'station' in scene or 'platform' in scene:
                 base.extend(['bench', 'backpack', 'suitcase', 'handbag'])
                 if 'train' in scene or 'subway' in scene: base.append('train')
                 if 'bus' in scene: base.append('bus')
            if 'airport' in scene or 'airfield' in scene:
                base.extend(['airplane', 'suitcase', 'handbag'])

            # Indoor / Home
            if any(x in scene for x in ['living_room', 'lounge', 'waiting_room', 'lobby']):
                base.extend(['chair', 'couch', 'potted plant', 'tv', 'book', 'clock', 'vase', 'cat', 'dog'])
            if 'kitchen' in scene or 'diner' in scene or 'restaurant' in scene or 'bar' in scene:
                base.extend(['bottle', 'cup', 'bowl', 'fork', 'knife', 'spoon', 'wine glass', 'chair', 'dining table'])
                if 'kitchen' in scene: base.extend(['microwave', 'oven', 'toaster', 'sink', 'refrigerator'])
                if 'bar' in scene: base.append('bottle')
            if 'bedroom' in scene or 'dorm' in scene:
                base.extend(['bed', 'clock', 'book', 'cell phone', 'teddy bear'])
            if 'bathroom' in scene or 'shower' in scene:
                base.extend(['toilet', 'sink', 'toothbrush', 'hair drier'])
            if 'office' in scene or 'computer' in scene or 'studio' in scene:
                base.extend(['chair', 'laptop', 'mouse', 'keyboard', 'book', 'cell phone', 'scissors'])
            
            # Sports / Rec
            if 'ball' in scene or 'field' in scene or 'stadium' in scene or 'court' in scene:
                base.extend(['sports ball', 'baseball bat', 'baseball glove', 'tennis racket'])
            if 'park' in scene or 'garden' in scene:
                base.extend(['bench', 'bird', 'dog', 'bicycle', 'frisbee', 'kite'])

            # Animals
            if 'zoo' in scene or 'farm' in scene or 'stable' in scene:
                base.extend(['horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe'])

            # Remove duplicates and validate
            return list(set([c for c in base if c in YOLO_CLASSES]))

        try:
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None) # Skip header
                
                rows_to_insert = []
                for row in reader:
                    if not row: continue
                    # places365.csv format: category (path or name)
                    # e.g. /a/airfield OR airfield
                    raw_scene = row[0]
                    scene_name = raw_scene.split('/')[-1] # take 'airfield' from '/a/airfield'
                    
                    if not scene_name: continue

                    classes = get_classes(scene_name)
                    rows_to_insert.append((raw_scene, json.dumps(classes)))
                    
                    # Also map the simple name if different
                    if raw_scene != scene_name:
                         rows_to_insert.append((scene_name, json.dumps(classes)))

                cursor.executemany('''
                    INSERT OR IGNORE INTO scene_context (scene_name, yolo_classes) VALUES (?, ?)
                ''', rows_to_insert)
                
                print(f"[ContextManager] Seeded {len(rows_to_insert)} scene mappings.")
                conn.commit()

        except Exception as e:
            print(f"[ContextManager] Error reading CSV or seeding: {e}")
            # Fallback for critical demo scenes if CSV fails
            fallback_data = [
                ('living_room', json.dumps(['person', 'chair', 'couch', 'tv', 'potted plant', 'cat', 'dog'])),
                ('bedroom', json.dumps(['person', 'bed', 'book', 'clock', 'cell phone'])),
                ('kitchen', json.dumps(['person', 'bottle', 'cup', 'bowl', 'sink', 'oven', 'refrigerator'])),
                ('office', json.dumps(['person', 'chair', 'laptop', 'mouse', 'keyboard', 'cell phone'])),
            ]
            cursor.executemany('INSERT OR IGNORE INTO scene_context (scene_name, yolo_classes) VALUES (?, ?)', fallback_data)
            conn.commit()


    def get_context_for_scene(self, scene_name):
        """
        Return the context (classes, model_file) for a given scene.
        Returns: {'classes': [...], 'model': 'filename.pt'}
        """
        # Normalize scene name
        simple_name = scene_name.split('/')[-1].replace('_', ' ')
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Helper to query
            def query(name):
                cursor.execute('SELECT yolo_classes, model_file FROM scene_context WHERE scene_name = ?', (name,))
                return cursor.fetchone()

            row = query(scene_name)
            if not row:
                row = query(simple_name)
            if not row:
                 # Fuzzy match
                cursor.execute('SELECT scene_name, yolo_classes, model_file FROM scene_context')
                all_rows = cursor.fetchall()
                for db_scene, db_classes, db_model in all_rows:
                    if db_scene in scene_name or scene_name in db_scene:
                         return {'classes': json.loads(db_classes), 'model': db_model}
                
                # Default
                return {'classes': ["person"], 'model': 'yolov8s-worldv2.pt'}

            return {'classes': json.loads(row[0]), 'model': row[1]}

    # Legacy support
    def get_classes_for_scene(self, scene_name):
        return self.get_context_for_scene(scene_name)['classes']

    def update_scene(self, scene_name, classes_list, model_file=None):
        """Add or update a mapping."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            classes_json = json.dumps(classes_list)
            
            if model_file:
                cursor.execute('''
                    INSERT INTO scene_context (scene_name, yolo_classes, model_file) 
                    VALUES (?, ?, ?)
                    ON CONFLICT(scene_name) DO UPDATE SET 
                        yolo_classes=excluded.yolo_classes,
                        model_file=excluded.model_file
                ''', (scene_name, classes_json, model_file))
            else:
                 cursor.execute('''
                    INSERT INTO scene_context (scene_name, yolo_classes) 
                    VALUES (?, ?)
                    ON CONFLICT(scene_name) DO UPDATE SET 
                        yolo_classes=excluded.yolo_classes
                ''', (scene_name, classes_json))

            conn.commit()
            
    def get_all_scenes(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT scene_name, yolo_classes, model_file FROM scene_context ORDER BY scene_name')
            return [
                {'name': r[0], 'classes': json.loads(r[1]), 'model': r[2]} 
                for r in cursor.fetchall()
            ]
