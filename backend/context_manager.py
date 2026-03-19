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

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _get_table(self, vocabulary):
        """Map vocabulary name to table name."""
        return 'scene_context_objects365' if vocabulary == 'objects365' else 'scene_context'

    def _init_db(self):
        """Initialize the database and seed both tables if empty."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # ── COCO-80 table ─────────────────────────────────────────────────
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scene_context (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scene_name TEXT UNIQUE NOT NULL,
                    yolo_classes TEXT NOT NULL, -- JSON list of strings
                    model_file TEXT DEFAULT 'yolov8s-worldv2.pt'
                )
            ''')

            # Migration: add model_file column for existing DBs
            cursor.execute("PRAGMA table_info(scene_context)")
            columns = [info[1] for info in cursor.fetchall()]
            if 'model_file' not in columns:
                print("[ContextManager] Migrating DB: Adding model_file column to scene_context...")
                cursor.execute("ALTER TABLE scene_context ADD COLUMN model_file TEXT DEFAULT 'yolov8s-worldv2.pt'")

            conn.commit()

            # Seed COCO-80 if empty
            cursor.execute('SELECT COUNT(*) FROM scene_context')
            if cursor.fetchone()[0] == 0:
                self._seed_db(conn)

            # ── Objects365 table ──────────────────────────────────────────────
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scene_context_objects365 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scene_name TEXT UNIQUE NOT NULL,
                    yolo_classes TEXT NOT NULL,
                    model_file TEXT DEFAULT 'yolov8s-worldv2.pt'
                )
            ''')
            conn.commit()

            # Seed Objects365 if empty
            cursor.execute('SELECT COUNT(*) FROM scene_context_objects365')
            if cursor.fetchone()[0] == 0:
                self._seed_objects365(conn)

    def _seed_objects365(self, conn):
        """Seed scene_context_objects365 from context_new.db if available, else from CSV."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        src_db = os.path.join(base_dir, 'data', 'context_new.db')

        if os.path.exists(src_db):
            print(f"[ContextManager] Importing Objects365 context from {src_db}...")
            try:
                src_conn = sqlite3.connect(src_db)
                src_cur = src_conn.cursor()
                src_cur.execute('SELECT scene_name, yolo_classes, model_file FROM scene_context')
                rows = src_cur.fetchall()
                src_conn.close()

                cur = conn.cursor()
                cur.executemany(
                    'INSERT OR IGNORE INTO scene_context_objects365 (scene_name, yolo_classes, model_file) VALUES (?,?,?)',
                    rows
                )
                conn.commit()
                print(f"[ContextManager] Imported {len(rows)} Objects365 scene mappings.")
                return
            except Exception as e:
                print(f"[ContextManager] Failed to import from context_new.db: {e}. Will seed from CSV.")

        # Fallback: seed from CSV using Objects365 vocabulary
        print(f"[ContextManager] Seeding Objects365 table from CSV {self.csv_path}...")
        self._seed_objects365_from_csv(conn)

    def _seed_objects365_from_csv(self, conn):
        """Seed scene_context_objects365 directly from the Places365 CSV with Objects365 vocab."""
        OBJ365_SET = set([
            'person', 'sneakers', 'chair', 'other shoes', 'hat', 'car', 'lamp',
            'glasses', 'bottle', 'desk', 'cup', 'street lights', 'cabinet', 'handbag',
            'bracelet', 'plate', 'picture frame', 'helmet', 'book', 'gloves',
            'storage box', 'boat', 'leather shoes', 'flower', 'bench', 'potted plant',
            'bowl', 'flag', 'pillow', 'boots', 'vase', 'microphone', 'necklace',
            'ring', 'suv', 'wine glass', 'belt', 'monitor', 'backpack', 'umbrella',
            'traffic light', 'speaker', 'watch', 'tie', 'trash can', 'slippers',
            'bicycle', 'stool', 'barrel', 'van', 'couch', 'sandals', 'basket',
            'drum', 'pen', 'bus', 'bird', 'high heels', 'motorcycle', 'guitar',
            'carpet', 'cell phone', 'bread', 'camera', 'canned food', 'pots',
            'padlock', 'bag', 'microwave', 'surfboard', 'skis', 'suit', 'pig',
            'laptop', 'violin', 'fried egg', 'volleyball', 'tray', 'fishing rod',
            'horse', 'cutting board', 'tennis racket', 'wheelchair', 'folder',
            'dog', 'spoon', 'clock', 'pot', 'elephant', 'soccer ball', 'basketball',
            'keyboard', 'towel', 'machinery vehicle', 'cow', 'tv', 'faucet',
            'candle', 'stuffed animal', 'gas stove', 'cake', 'camel', 'sheep',
            'zebra', 'lemon', 'duck', 'banana', 'lantern', 'cat', 'pitcher',
            'airplane', 'watermelon', 'grape', 'sushi', 'skateboard', 'strawberry',
            'bow tie', 'face mask', 'seafood', 'cookies', 'orange', 'pasta',
            'pie', 'coconut', 'polar bear', 'koala', 'seal', 'rabbit', 'frog',
            'eagle', 'owl', 'apple', 'mango', 'kiwi', 'avocado', 'broccoli',
            'onion', 'tomato', 'corn', 'carrot', 'garlic', 'peppers', 'potato',
            'cucumber', 'cabbage', 'eggplant', 'pumpkin', 'pear', 'peach', 'plum',
            'cherry', 'mushroom', 'pineapple', 'hamburger', 'pizza', 'hot dog',
            'french fries', 'fried chicken', 'ice cream', 'donut', 'waffle',
            'sandwich', 'rice', 'noodles', 'dumplings', 'sausage', 'steak',
            'lobster', 'shrimp', 'crab', 'tofu', 'egg', 'milk', 'juice', 'tea',
            'coffee', 'beer', 'wine', 'cocktail', 'kettle', 'blender', 'toaster',
            'refrigerator', 'washing machine', 'vacuum cleaner', 'iron', 'fan',
            'air conditioner', 'tablet', 'printer', 'router', 'headphones',
            'remote control', 'game controller', 'projector', 'whiteboard',
            'blackboard', 'pencil case', 'ruler', 'eraser', 'stapler', 'scissors',
            'tape', 'marker', 'notebook', 'magazine', 'newspaper', 'suitcase',
            'wallet', 'key', 'lock', 'safe', 'shelf', 'drawer', 'wardrobe',
            'bed', 'blanket', 'mattress', 'curtain', 'mirror', 'rug', 'sink',
            'toilet', 'bathtub', 'shower', 'soap', 'toothbrush', 'toothpaste',
            'shampoo', 'razor', 'comb', 'lipstick', 'medicine', 'bandage',
            'thermometer', 'stethoscope', 'syringe', 'crutch', 'firework',
            'balloon', 'kite', 'frisbee', 'baseball', 'football', 'rugby ball',
            'golf club', 'golf ball', 'boxing gloves', 'medal', 'trophy',
            'map', 'binoculars', 'hammer', 'screwdriver', 'wrench', 'pliers',
            'saw', 'drill', 'paintbrush', 'palette', 'piano', 'trumpet', 'flute',
            'saxophone', 'harmonica', 'ukulele', 'traffic cone', 'road sign',
            'parking meter', 'fire hydrant', 'mailbox', 'fountain', 'statue',
            'train', 'truck', 'stop sign', 'fork', 'knife',
        ])

        CATEGORY_CLASSES = {
            0:  ['chair', 'stool', 'desk', 'plate', 'cup', 'wine glass', 'bottle', 'bowl', 'fork', 'knife', 'spoon', 'tray', 'basket', 'bag', 'handbag', 'bread', 'cake', 'pizza', 'hamburger', 'hot dog', 'sandwich', 'donut', 'ice cream', 'juice', 'coffee', 'tea', 'beer', 'wine', 'cocktail', 'storage box', 'canned food', 'cookies'],
            1:  ['chair', 'desk', 'laptop', 'keyboard', 'monitor', 'tablet', 'printer', 'router', 'book', 'notebook', 'folder', 'pen', 'scissors', 'ruler', 'stapler', 'eraser', 'pencil case', 'marker', 'clock', 'cell phone', 'magazine', 'whiteboard', 'blackboard', 'projector', 'speaker', 'headphones', 'cabinet'],
            2:  ['chair', 'couch', 'bed', 'pillow', 'blanket', 'mattress', 'curtain', 'mirror', 'rug', 'carpet', 'tv', 'remote control', 'clock', 'vase', 'potted plant', 'book', 'cup', 'bottle', 'lamp', 'shelf', 'drawer', 'wardrobe', 'cabinet', 'stool', 'picture frame', 'candle', 'fan', 'air conditioner'],
            3:  ['suitcase', 'backpack', 'handbag', 'bench', 'cell phone', 'umbrella', 'book', 'notebook', 'bag', 'clock', 'tv', 'headphones'],
            4:  ['soccer ball', 'basketball', 'volleyball', 'tennis racket', 'baseball', 'football', 'rugby ball', 'skateboard', 'surfboard', 'skis', 'frisbee', 'kite', 'golf club', 'golf ball', 'boxing gloves', 'bench', 'trophy', 'medal', 'backpack', 'bottle', 'towel', 'fishing rod', 'bicycle'],
            5:  ['book', 'notebook', 'pen', 'clock', 'vase', 'chair', 'stool', 'potted plant', 'backpack', 'flag', 'statue', 'picture frame', 'lantern', 'candle', 'whiteboard', 'blackboard'],
            6:  ['boat', 'surfboard', 'umbrella', 'skis', 'bird', 'fishing rod', 'backpack'],
            7:  ['backpack', 'bottle', 'bird', 'eagle', 'owl', 'map', 'binoculars', 'flag'],
            8:  ['bird', 'dog', 'cat', 'horse', 'cow', 'sheep', 'pig', 'rabbit', 'frog', 'eagle', 'owl', 'backpack', 'bottle', 'basket', 'bicycle'],
            9:  ['bench', 'clock', 'potted plant', 'fire hydrant', 'traffic light', 'street lights', 'traffic cone', 'road sign', 'stop sign', 'parking meter', 'mailbox', 'trash can', 'fountain', 'statue'],
            10: ['car', 'suv', 'van', 'bus', 'truck', 'motorcycle', 'bicycle', 'traffic light', 'stop sign', 'parking meter', 'airplane', 'boat', 'train', 'road sign', 'traffic cone', 'helmet'],
            11: ['bench', 'clock', 'vase', 'potted plant', 'book', 'flag', 'statue', 'lantern', 'candle', 'picture frame', 'fountain'],
            12: ['bench', 'bicycle', 'dog', 'bird', 'frisbee', 'kite', 'soccer ball', 'basketball', 'volleyball', 'skateboard', 'backpack', 'bottle', 'umbrella', 'potted plant', 'trash can'],
            13: ['truck', 'van', 'machinery vehicle', 'car', 'backpack', 'hammer', 'wrench', 'drill', 'saw', 'helmet', 'storage box', 'barrel'],
            14: ['horse', 'sheep', 'cow', 'pig', 'dog', 'cat', 'bird', 'duck', 'rabbit', 'potted plant', 'bench', 'bicycle', 'basket', 'flower', 'vase'],
            15: ['car', 'suv', 'van', 'bus', 'truck', 'motorcycle', 'bicycle', 'handbag', 'backpack', 'umbrella', 'bench', 'traffic light', 'cell phone', 'bottle', 'bag', 'street lights', 'trash can', 'traffic cone', 'stop sign'],
        }

        KEYWORD_CLASSES = {
            'kitchen':      ['microwave', 'toaster', 'refrigerator', 'faucet', 'kettle', 'blender', 'gas stove', 'cutting board', 'bowl', 'cup', 'bottle', 'plate', 'fork', 'knife', 'spoon', 'pot', 'pots', 'tray', 'chair', 'stool', 'desk'],
            'dining':       ['desk', 'chair', 'fork', 'knife', 'spoon', 'bowl', 'cup', 'wine glass', 'bottle', 'plate', 'vase', 'candle'],
            'restaurant':   ['chair', 'stool', 'desk', 'fork', 'knife', 'spoon', 'bowl', 'cup', 'wine glass', 'bottle', 'plate', 'tray', 'vase', 'candle'],
            'cafeteria':    ['chair', 'stool', 'desk', 'cup', 'bowl', 'bottle', 'fork', 'knife', 'spoon', 'tray', 'bread', 'cake'],
            'bar':          ['bottle', 'wine glass', 'cup', 'chair', 'stool', 'tv', 'beer', 'cocktail', 'candle'],
            'pub':          ['bottle', 'wine glass', 'cup', 'beer', 'chair', 'tv'],
            'bakery':       ['cake', 'donut', 'bread', 'cookies', 'bottle', 'bowl', 'tray', 'basket'],
            'pizzeria':     ['pizza', 'bottle', 'cup', 'chair', 'fork', 'knife'],
            'deli':         ['sandwich', 'bread', 'bottle', 'bowl', 'tray'],
            'supermarket':  ['bottle', 'banana', 'apple', 'orange', 'broccoli', 'carrot', 'cake', 'basket', 'bag', 'canned food', 'pineapple', 'watermelon', 'bread', 'cookies'],
            'market':       ['bottle', 'banana', 'apple', 'orange', 'umbrella', 'handbag', 'backpack', 'basket', 'flower', 'vase'],
            'grocery':      ['bottle', 'banana', 'apple', 'orange', 'broccoli', 'carrot', 'pineapple', 'basket', 'bag'],
            'food':         ['bowl', 'cup', 'bottle', 'fork', 'knife', 'spoon', 'banana', 'apple', 'sandwich', 'orange', 'pizza', 'cake', 'donut', 'bread', 'hamburger', 'hot dog'],
            'bedroom':      ['bed', 'pillow', 'blanket', 'mattress', 'clock', 'book', 'cell phone', 'stuffed animal', 'lamp', 'laptop', 'remote control', 'tv', 'curtain', 'mirror', 'wardrobe', 'drawer'],
            'dorm':         ['bed', 'chair', 'laptop', 'book', 'cell phone', 'clock', 'backpack', 'mirror', 'lamp'],
            'nursery':      ['bed', 'stuffed animal', 'book', 'clock', 'chair', 'pillow', 'blanket'],
            'living_room':  ['couch', 'chair', 'tv', 'remote control', 'potted plant', 'book', 'clock', 'vase', 'cat', 'dog', 'carpet', 'lamp', 'pillow', 'blanket', 'curtain', 'magazine'],
            'lounge':       ['couch', 'chair', 'tv', 'remote control', 'bottle', 'cup', 'clock', 'lamp', 'potted plant'],
            'lobby':        ['couch', 'chair', 'potted plant', 'suitcase', 'clock', 'vase', 'lamp', 'mirror', 'statue'],
            'waiting_room': ['chair', 'bench', 'book', 'magazine', 'cell phone', 'clock', 'tv', 'backpack', 'bag'],
            'bathroom':     ['toilet', 'sink', 'faucet', 'bathtub', 'shower', 'toothbrush', 'toothpaste', 'razor', 'shampoo', 'soap', 'mirror', 'towel', 'bottle', 'cup', 'comb'],
            'laundry':      ['bottle', 'washing machine', 'basket'],
            'office':       ['chair', 'laptop', 'keyboard', 'monitor', 'tablet', 'book', 'notebook', 'folder', 'pen', 'cell phone', 'scissors', 'clock', 'tv', 'printer', 'speaker', 'whiteboard', 'ruler', 'stapler'],
            'computer':     ['laptop', 'keyboard', 'monitor', 'tablet', 'chair', 'cell phone', 'tv', 'speaker', 'headphones'],
            'conference':   ['chair', 'laptop', 'tv', 'projector', 'bottle', 'cup', 'cell phone', 'clock', 'book', 'whiteboard', 'marker'],
            'classroom':    ['chair', 'book', 'notebook', 'pen', 'laptop', 'backpack', 'clock', 'tv', 'whiteboard', 'blackboard', 'ruler', 'marker', 'eraser'],
            'lecture':      ['chair', 'laptop', 'book', 'backpack', 'clock', 'projector', 'whiteboard', 'blackboard', 'microphone'],
            'library':      ['book', 'notebook', 'magazine', 'newspaper', 'chair', 'laptop', 'backpack', 'clock', 'lamp', 'shelf'],
            'studio':       ['chair', 'laptop', 'keyboard', 'monitor', 'book', 'cell phone', 'scissors', 'tv', 'camera', 'microphone', 'speaker', 'headphones'],
            'lab':          ['laptop', 'keyboard', 'monitor', 'chair', 'bottle', 'book', 'clock', 'cell phone', 'stethoscope', 'syringe', 'thermometer'],
            'parking':      ['car', 'suv', 'van', 'truck', 'motorcycle', 'bicycle', 'traffic light', 'stop sign', 'parking meter', 'traffic cone', 'road sign'],
            'garage':       ['car', 'suv', 'van', 'truck', 'motorcycle', 'bicycle', 'hammer', 'wrench', 'drill'],
            'highway':      ['car', 'suv', 'van', 'bus', 'truck', 'motorcycle', 'traffic light', 'road sign', 'traffic cone'],
            'street':       ['car', 'suv', 'van', 'bus', 'truck', 'bicycle', 'motorcycle', 'traffic light', 'stop sign', 'fire hydrant', 'bench', 'dog', 'street lights', 'trash can', 'traffic cone', 'mailbox', 'umbrella'],
            'road':         ['car', 'suv', 'bus', 'truck', 'motorcycle', 'bicycle', 'traffic light', 'stop sign', 'road sign', 'traffic cone'],
            'crosswalk':    ['car', 'bus', 'traffic light', 'bicycle', 'stop sign'],
            'intersection': ['car', 'suv', 'bus', 'truck', 'traffic light', 'stop sign', 'bicycle', 'road sign'],
            'bridge':       ['car', 'bus', 'truck', 'boat', 'bicycle'],
            'driveway':     ['car', 'suv', 'truck', 'bicycle', 'motorcycle'],
            'airport':      ['airplane', 'suitcase', 'backpack', 'handbag', 'bench', 'cell phone', 'tv', 'umbrella', 'bag', 'clock'],
            'airfield':     ['airplane', 'suv', 'van', 'truck'],
            'runway':       ['airplane'],
            'hangar':       ['airplane', 'truck', 'machinery vehicle'],
            'train':        ['train', 'suitcase', 'backpack', 'bench', 'bag'],
            'subway':       ['train', 'bench', 'backpack', 'cell phone', 'bag'],
            'harbor':       ['boat', 'truck', 'barrel'],
            'marina':       ['boat'],
            'dock':         ['boat', 'barrel'],
            'pier':         ['boat', 'bench', 'bird', 'fishing rod'],
            'swimming':     ['bench', 'towel', 'bottle', 'umbrella'],
            'pool':         ['bench', 'umbrella', 'chair', 'towel', 'bottle'],
            'gym':          ['bench', 'backpack', 'bottle', 'towel', 'trophy', 'basketball', 'volleyball', 'soccer ball'],
            'tennis':       ['tennis racket', 'soccer ball', 'bench', 'backpack', 'bottle', 'towel'],
            'basketball':   ['basketball', 'bench', 'backpack', 'bottle'],
            'baseball':     ['baseball', 'bench', 'backpack', 'helmet', 'gloves'],
            'soccer':       ['soccer ball', 'bench', 'backpack', 'bottle'],
            'football':     ['football', 'rugby ball', 'bench', 'helmet'],
            'ski':          ['skis', 'helmet', 'gloves', 'backpack'],
            'ice':          ['skis', 'helmet', 'gloves'],
            'stadium':      ['soccer ball', 'basketball', 'bench', 'backpack', 'bottle', 'trophy', 'flag', 'speaker'],
            'arena':        ['bench', 'chair', 'backpack', 'flag', 'trophy', 'microphone', 'speaker'],
            'playground':   ['bench', 'bicycle', 'dog', 'skateboard', 'basketball', 'kite', 'frisbee', 'balloon'],
            'park':         ['bench', 'bird', 'dog', 'bicycle', 'frisbee', 'kite', 'potted plant', 'flower', 'umbrella', 'trash can'],
            'garden':       ['bench', 'bird', 'potted plant', 'dog', 'cat', 'vase', 'flower', 'basket'],
            'yard':         ['bench', 'dog', 'cat', 'bird', 'bicycle', 'potted plant', 'basket', 'flower'],
            'patio':        ['chair', 'bench', 'potted plant', 'umbrella', 'dog', 'cat', 'bottle', 'vase', 'flower'],
            'balcony':      ['chair', 'potted plant', 'umbrella', 'bicycle', 'flower'],
            'zoo':          ['elephant', 'camel', 'zebra', 'polar bear', 'koala', 'seal', 'bird', 'eagle', 'owl', 'bench', 'backpack', 'bottle'],
            'farm':         ['horse', 'sheep', 'cow', 'pig', 'dog', 'cat', 'bird', 'duck', 'rabbit', 'truck', 'basket'],
            'stable':       ['horse', 'dog', 'basket'],
            'kennel':       ['dog', 'cat', 'rabbit'],
            'pasture':      ['horse', 'sheep', 'cow', 'dog', 'bird', 'duck'],
            'forest':       ['bird', 'dog', 'eagle', 'owl', 'backpack', 'bottle', 'mushroom', 'basket'],
            'field':        ['bird', 'dog', 'cow', 'horse', 'sheep', 'bicycle', 'backpack'],
            'mountain':     ['backpack', 'bottle', 'map', 'binoculars', 'bird', 'eagle', 'flag'],
            'beach':        ['umbrella', 'surfboard', 'boat', 'bird', 'dog', 'frisbee', 'kite', 'towel', 'backpack', 'bottle', 'sandals'],
            'ocean':        ['boat', 'surfboard', 'bird', 'umbrella'],
            'lake':         ['boat', 'bird', 'fishing rod', 'duck'],
            'river':        ['boat', 'bird', 'fishing rod', 'duck'],
            'shop':         ['bottle', 'handbag', 'backpack', 'cell phone', 'umbrella', 'bag', 'basket', 'watch', 'glasses'],
            'store':        ['bottle', 'handbag', 'backpack', 'cell phone', 'bag', 'shelf', 'storage box'],
            'mall':         ['handbag', 'backpack', 'cell phone', 'umbrella', 'bench', 'potted plant', 'bag', 'watch', 'glasses'],
            'hotel':        ['bed', 'chair', 'couch', 'tv', 'remote control', 'suitcase', 'clock', 'vase', 'potted plant', 'lamp', 'pillow', 'blanket', 'mirror', 'curtain'],
            'hospital':     ['bed', 'chair', 'tv', 'clock', 'bottle', 'cell phone', 'wheelchair', 'crutch', 'stethoscope', 'syringe', 'thermometer', 'bandage', 'medicine', 'pillow'],
            'pharmacy':     ['bottle', 'medicine', 'bandage'],
            'dentist':      ['chair', 'tv', 'medicine'],
            'church':       ['bench', 'book', 'clock', 'vase', 'candle', 'flower', 'flag', 'lantern'],
            'temple':       ['bench', 'vase', 'potted plant', 'lantern', 'candle', 'statue', 'flower'],
            'mosque':       ['clock', 'vase', 'book', 'lantern', 'candle'],
            'museum':       ['bench', 'vase', 'clock', 'book', 'potted plant', 'statue', 'picture frame', 'flag'],
            'gallery':      ['vase', 'bench', 'potted plant', 'picture frame', 'statue'],
            'theater':      ['chair', 'microphone', 'speaker', 'camera', 'curtain'],
            'cinema':       ['chair', 'tv', 'cup', 'bottle', 'projector'],
            'casino':       ['chair', 'cup', 'bottle', 'tv'],
            'banquet':      ['chair', 'fork', 'knife', 'spoon', 'vase', 'wine glass', 'bottle', 'cup', 'candle', 'flower'],
            'ballroom':     ['chair', 'clock', 'vase', 'lamp', 'microphone', 'speaker', 'flower'],
            'corridor':     ['fire hydrant', 'clock', 'potted plant', 'trash can', 'street lights'],
            'hallway':      ['clock', 'potted plant', 'vase', 'lamp', 'mirror'],
            'staircase':    ['backpack', 'handbag', 'trash can'],
            'elevator':     ['cell phone', 'backpack', 'mirror'],
            'closet':       ['handbag', 'backpack', 'umbrella', 'tie', 'belt', 'boots', 'sneakers', 'high heels', 'suit'],
            'attic':        ['suitcase', 'book', 'clock', 'stuffed animal'],
            'basement':     ['bicycle', 'suitcase', 'bottle', 'barrel', 'storage box'],
            'cabin':        ['bed', 'chair', 'book', 'clock', 'cup', 'lamp', 'blanket', 'pillow'],
            'cottage':      ['chair', 'potted plant', 'dog', 'cat', 'bed', 'flower', 'vase'],
            'veranda':      ['chair', 'bench', 'potted plant', 'dog', 'cat', 'flower', 'umbrella'],
            'kindergarten': ['chair', 'book', 'stuffed animal', 'backpack', 'clock', 'balloon', 'pencil case'],
            'playroom':     ['stuffed animal', 'book', 'tv', 'chair', 'balloon', 'basketball', 'soccer ball'],
            'construction': ['truck', 'machinery vehicle', 'hammer', 'wrench', 'drill', 'saw', 'helmet', 'barrel', 'storage box', 'traffic cone'],
            'factory':      ['truck', 'machinery vehicle', 'chair', 'helmet', 'storage box', 'barrel'],
            'warehouse':    ['truck', 'bicycle', 'storage box', 'barrel', 'shelf'],
            'concert':      ['guitar', 'violin', 'piano', 'drum', 'trumpet', 'saxophone', 'microphone', 'speaker', 'headphones', 'bench', 'flag'],
            'music':        ['guitar', 'violin', 'piano', 'drum', 'trumpet', 'saxophone', 'harmonica', 'ukulele', 'microphone', 'speaker', 'headphones'],
        }

        def get_classes(scene_name, category_flags):
            classes = {'person'}
            for idx, flag in enumerate(category_flags):
                if flag == 1 and idx in CATEGORY_CLASSES:
                    classes.update(CATEGORY_CLASSES[idx])
            scene_lower = scene_name.lower()
            scene_words = set(scene_lower.split('_'))
            for keyword, kw_classes in KEYWORD_CLASSES.items():
                if keyword in scene_words or ('_' in keyword and keyword in scene_lower):
                    classes.update(kw_classes)
            return sorted(c for c in classes if c in OBJ365_SET)

        try:
            rows_to_insert = []
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)
                next(reader, None)
                for row in reader:
                    if not row or len(row) < 4:
                        continue
                    raw_scene = row[0].strip().strip("'\"")
                    if not raw_scene or raw_scene == 'category':
                        continue
                    parts = [p for p in raw_scene.split('/') if p and len(p) > 1]
                    scene_name = '_'.join(parts)
                    category_flags = []
                    for i in range(4, min(20, len(row))):
                        try:
                            category_flags.append(int(row[i]))
                        except (ValueError, IndexError):
                            category_flags.append(0)
                    classes = get_classes(scene_name, category_flags)
                    rows_to_insert.append((scene_name, json.dumps(classes)))

            cursor = conn.cursor()
            cursor.executemany(
                'INSERT OR IGNORE INTO scene_context_objects365 (scene_name, yolo_classes) VALUES (?, ?)',
                rows_to_insert
            )
            conn.commit()
            print(f"[ContextManager] Seeded {len(rows_to_insert)} Objects365 scene mappings from CSV.")

        except Exception as e:
            print(f"[ContextManager] Error seeding Objects365 from CSV: {e}")
            import traceback
            traceback.print_exc()

    def _seed_db(self, conn):
        print(f"[ContextManager] Seeding COCO-80 database from {self.csv_path}...")
        cursor = conn.cursor()

        YOLO_CLASSES = set([
            'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat', 'traffic light',
            'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat', 'dog', 'horse', 'sheep', 'cow',
            'elephant', 'bear', 'zebra', 'giraffe', 'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee',
            'skis', 'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard',
            'tennis racket', 'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple',
            'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch',
            'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse', 'remote', 'keyboard',
            'cell phone', 'microwave', 'oven', 'toaster', 'sink', 'refrigerator', 'book', 'clock', 'vase',
            'scissors', 'teddy bear', 'hair drier', 'toothbrush',
        ])

        CATEGORY_CLASSES = {
            0:  ['chair', 'dining table', 'bottle', 'cup', 'wine glass', 'fork', 'knife', 'spoon', 'bowl'],
            1:  ['chair', 'laptop', 'keyboard', 'mouse', 'cell phone', 'book', 'clock', 'scissors', 'tv'],
            2:  ['chair', 'couch', 'bed', 'tv', 'remote', 'clock', 'vase', 'potted plant', 'book', 'cup', 'bottle'],
            3:  ['suitcase', 'backpack', 'handbag', 'bench', 'cell phone', 'umbrella'],
            4:  ['sports ball', 'tennis racket', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard', 'frisbee', 'kite', 'skis', 'snowboard', 'bench'],
            5:  ['book', 'clock', 'vase', 'chair', 'potted plant', 'backpack'],
            6:  ['boat', 'surfboard', 'umbrella'],
            7:  ['backpack'],
            8:  ['bird', 'dog', 'cat', 'backpack'],
            9:  ['bench', 'clock', 'potted plant', 'fire hydrant', 'traffic light'],
            10: ['car', 'bus', 'truck', 'motorcycle', 'bicycle', 'traffic light', 'stop sign', 'parking meter', 'airplane', 'boat', 'train'],
            11: ['bench', 'clock', 'vase', 'potted plant', 'book'],
            12: ['bench', 'bicycle', 'dog', 'bird', 'frisbee', 'kite', 'sports ball', 'skateboard'],
            13: ['truck', 'car', 'backpack'],
            14: ['horse', 'sheep', 'cow', 'dog', 'cat', 'bird', 'potted plant', 'bench', 'bicycle'],
            15: ['car', 'bus', 'truck', 'bicycle', 'motorcycle', 'handbag', 'backpack', 'umbrella', 'bench', 'traffic light', 'cell phone', 'bottle'],
        }

        KEYWORD_CLASSES = {
            'kitchen':      ['microwave', 'oven', 'toaster', 'sink', 'refrigerator', 'bowl', 'cup', 'bottle', 'fork', 'knife', 'spoon', 'dining table', 'chair'],
            'dining':       ['dining table', 'chair', 'fork', 'knife', 'spoon', 'bowl', 'cup', 'wine glass', 'bottle'],
            'restaurant':   ['dining table', 'chair', 'fork', 'knife', 'spoon', 'bowl', 'cup', 'wine glass', 'bottle'],
            'cafeteria':    ['dining table', 'chair', 'cup', 'bowl', 'bottle', 'fork', 'knife', 'spoon'],
            'bar':          ['bottle', 'wine glass', 'cup', 'chair', 'tv'],
            'pub':          ['bottle', 'wine glass', 'cup', 'chair', 'tv'],
            'food':         ['bowl', 'cup', 'bottle', 'fork', 'knife', 'spoon', 'banana', 'apple', 'sandwich', 'orange', 'pizza', 'cake', 'donut'],
            'bakery':       ['cake', 'donut', 'bottle', 'bowl', 'dining table'],
            'pizzeria':     ['pizza', 'bottle', 'cup', 'dining table', 'chair'],
            'deli':         ['sandwich', 'bottle', 'bowl', 'dining table'],
            'supermarket':  ['bottle', 'banana', 'apple', 'orange', 'broccoli', 'carrot', 'cake'],
            'market':       ['bottle', 'banana', 'apple', 'orange', 'umbrella', 'handbag', 'backpack'],
            'grocery':      ['bottle', 'banana', 'apple', 'orange', 'broccoli', 'carrot'],
            'bedroom':      ['bed', 'clock', 'book', 'cell phone', 'teddy bear', 'laptop', 'remote', 'tv'],
            'dorm':         ['bed', 'chair', 'laptop', 'book', 'cell phone', 'clock', 'backpack'],
            'nursery':      ['bed', 'teddy bear', 'book', 'clock', 'chair'],
            'living_room':  ['couch', 'chair', 'tv', 'remote', 'potted plant', 'book', 'clock', 'vase', 'cat', 'dog'],
            'lounge':       ['couch', 'chair', 'tv', 'remote', 'bottle', 'cup', 'clock'],
            'lobby':        ['couch', 'chair', 'potted plant', 'suitcase', 'clock', 'vase'],
            'waiting_room': ['chair', 'bench', 'book', 'cell phone', 'clock', 'tv', 'backpack'],
            'bathroom':     ['toilet', 'sink', 'toothbrush', 'hair drier', 'bottle', 'cup'],
            'shower':       ['bottle'],
            'laundry':      ['bottle'],
            'office':       ['chair', 'laptop', 'keyboard', 'mouse', 'book', 'cell phone', 'scissors', 'clock', 'tv'],
            'computer':     ['laptop', 'keyboard', 'mouse', 'chair', 'cell phone', 'tv'],
            'conference':   ['chair', 'laptop', 'tv', 'bottle', 'cup', 'cell phone', 'clock', 'book'],
            'classroom':    ['chair', 'book', 'laptop', 'backpack', 'clock', 'tv'],
            'lecture':      ['chair', 'laptop', 'book', 'backpack', 'clock'],
            'library':      ['book', 'chair', 'laptop', 'backpack', 'clock'],
            'studio':       ['chair', 'laptop', 'keyboard', 'mouse', 'book', 'cell phone', 'scissors', 'tv'],
            'parking':      ['car', 'truck', 'motorcycle', 'bicycle', 'traffic light', 'stop sign', 'parking meter'],
            'garage':       ['car', 'truck', 'motorcycle', 'bicycle'],
            'highway':      ['car', 'bus', 'truck', 'motorcycle', 'traffic light'],
            'street':       ['car', 'bus', 'truck', 'bicycle', 'motorcycle', 'traffic light', 'stop sign', 'fire hydrant', 'bench', 'dog'],
            'road':         ['car', 'bus', 'truck', 'motorcycle', 'bicycle', 'traffic light', 'stop sign'],
            'crosswalk':    ['car', 'bus', 'traffic light', 'bicycle'],
            'intersection': ['car', 'bus', 'truck', 'traffic light', 'stop sign', 'bicycle'],
            'bridge':       ['car', 'bus', 'truck', 'boat'],
            'driveway':     ['car', 'truck', 'bicycle'],
            'airport':      ['airplane', 'suitcase', 'backpack', 'handbag', 'bench', 'cell phone', 'tv'],
            'airfield':     ['airplane'],
            'runway':       ['airplane'],
            'hangar':       ['airplane', 'truck'],
            'train':        ['train', 'suitcase', 'backpack', 'bench'],
            'subway':       ['train', 'bench', 'backpack', 'cell phone'],
            'bus':          ['bus', 'backpack', 'suitcase', 'bench', 'cell phone'],
            'harbor':       ['boat', 'truck'],
            'marina':       ['boat'],
            'dock':         ['boat'],
            'pier':         ['boat', 'bench', 'bird'],
            'swimming':     ['bench'],
            'pool':         ['bench', 'umbrella', 'chair'],
            'gym':          ['bench', 'backpack', 'bottle', 'sports ball'],
            'tennis':       ['tennis racket', 'sports ball', 'bench'],
            'basketball':   ['sports ball', 'bench', 'backpack'],
            'baseball':     ['baseball bat', 'baseball glove', 'sports ball', 'bench'],
            'soccer':       ['sports ball', 'bench', 'backpack'],
            'football':     ['sports ball', 'bench'],
            'ski':          ['skis', 'snowboard', 'backpack'],
            'ice':          ['skis'],
            'stadium':      ['sports ball', 'bench', 'backpack', 'bottle'],
            'arena':        ['bench', 'chair', 'backpack'],
            'playground':   ['bench', 'bicycle', 'dog', 'skateboard'],
            'park':         ['bench', 'bird', 'dog', 'bicycle', 'frisbee', 'kite', 'potted plant'],
            'garden':       ['bench', 'bird', 'potted plant', 'dog', 'cat', 'vase'],
            'yard':         ['bench', 'dog', 'cat', 'bird', 'bicycle', 'potted plant'],
            'patio':        ['chair', 'bench', 'potted plant', 'umbrella', 'dog', 'cat', 'bottle'],
            'balcony':      ['chair', 'potted plant', 'umbrella', 'bicycle'],
            'zoo':          ['elephant', 'bear', 'zebra', 'giraffe', 'bird', 'bench'],
            'farm':         ['horse', 'sheep', 'cow', 'dog', 'cat', 'bird', 'truck'],
            'stable':       ['horse', 'dog'],
            'kennel':       ['dog'],
            'pasture':      ['horse', 'sheep', 'cow', 'dog'],
            'forest':       ['bird', 'dog', 'backpack'],
            'field':        ['bird', 'dog', 'cow', 'horse', 'sheep'],
            'mountain':     ['backpack'],
            'beach':        ['umbrella', 'surfboard', 'boat', 'bird', 'dog', 'frisbee', 'kite'],
            'ocean':        ['boat', 'surfboard', 'bird'],
            'lake':         ['boat', 'bird'],
            'river':        ['boat', 'bird'],
            'shop':         ['bottle', 'handbag', 'backpack', 'cell phone', 'umbrella'],
            'store':        ['bottle', 'handbag', 'backpack', 'cell phone'],
            'mall':         ['handbag', 'backpack', 'cell phone', 'umbrella', 'bench', 'potted plant'],
            'hotel':        ['bed', 'chair', 'couch', 'tv', 'remote', 'suitcase', 'clock', 'vase', 'potted plant'],
            'hospital':     ['bed', 'chair', 'tv', 'clock', 'bottle', 'cell phone'],
            'pharmacy':     ['bottle'],
            'dentist':      ['chair', 'tv'],
            'church':       ['bench', 'book', 'clock', 'vase'],
            'temple':       ['bench', 'vase', 'potted plant'],
            'mosque':       ['clock', 'vase', 'book'],
            'museum':       ['bench', 'vase', 'clock', 'book', 'potted plant'],
            'gallery':      ['vase', 'bench', 'potted plant'],
            'theater':      ['chair'],
            'cinema':       ['chair', 'tv', 'cup', 'bottle'],
            'casino':       ['chair', 'cup', 'bottle', 'tv'],
            'banquet':      ['dining table', 'chair', 'wine glass', 'bottle', 'cup', 'fork', 'knife', 'spoon', 'vase'],
            'ballroom':     ['chair', 'clock', 'vase'],
            'corridor':     ['fire hydrant', 'clock', 'potted plant'],
            'hallway':      ['clock', 'potted plant', 'vase'],
            'staircase':    ['backpack'],
            'elevator':     ['cell phone', 'backpack'],
            'closet':       ['handbag', 'backpack', 'umbrella', 'tie'],
            'attic':        ['suitcase', 'book', 'clock', 'teddy bear'],
            'basement':     ['bicycle', 'suitcase', 'bottle'],
            'cabin':        ['bed', 'chair', 'book', 'clock', 'cup'],
            'cottage':      ['chair', 'potted plant', 'dog', 'cat', 'bed'],
            'veranda':      ['chair', 'bench', 'potted plant', 'dog', 'cat'],
            'kindergarten': ['chair', 'book', 'teddy bear', 'backpack', 'clock'],
            'playroom':     ['teddy bear', 'book', 'tv', 'chair'],
            'toyshop':      ['teddy bear', 'bicycle', 'skateboard', 'book'],
            'construction': ['truck'],
            'factory':      ['truck', 'chair'],
            'warehouse':    ['truck', 'bicycle'],
            'lab':          ['laptop', 'keyboard', 'mouse', 'chair', 'bottle', 'book', 'clock', 'cell phone'],
            'auto':         ['car', 'truck'],
            'car':          ['car'],
            'cab':          ['car', 'cell phone', 'backpack'],
            'limousine':    ['car'],
            'cockpit':      ['airplane'],
            'boat':         ['boat'],
        }

        def get_classes(scene_name, category_flags):
            classes = set(['person'])
            for idx, flag in enumerate(category_flags):
                if flag == 1 and idx in CATEGORY_CLASSES:
                    classes.update(CATEGORY_CLASSES[idx])
            scene_lower = scene_name.lower()
            scene_words = set(scene_lower.split('_'))
            for keyword, kw_classes in KEYWORD_CLASSES.items():
                if keyword in scene_words or ('_' in keyword and keyword in scene_lower):
                    classes.update(kw_classes)
            return sorted([c for c in classes if c in YOLO_CLASSES])

        try:
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)
                next(reader, None)
                rows_to_insert = []
                for row in reader:
                    if not row or len(row) < 4:
                        continue
                    raw_scene = row[0].strip().strip("'\"")
                    if not raw_scene or raw_scene == 'category':
                        continue
                    parts = [p for p in raw_scene.split('/') if p and len(p) > 1]
                    scene_name = '_'.join(parts)
                    category_flags = []
                    for i in range(4, min(20, len(row))):
                        try:
                            category_flags.append(int(row[i]))
                        except (ValueError, IndexError):
                            category_flags.append(0)
                    classes = get_classes(scene_name, category_flags)
                    rows_to_insert.append((scene_name, json.dumps(classes)))

                cursor.executemany(
                    'INSERT OR IGNORE INTO scene_context (scene_name, yolo_classes) VALUES (?, ?)',
                    rows_to_insert
                )
                print(f"[ContextManager] Seeded {len(rows_to_insert)} COCO-80 scene mappings.")
                conn.commit()

        except Exception as e:
            print(f"[ContextManager] Error reading CSV or seeding: {e}")
            import traceback
            traceback.print_exc()
            fallback_data = [
                ('living_room', json.dumps(['person', 'chair', 'couch', 'tv', 'remote', 'potted plant', 'cat', 'dog', 'book', 'clock', 'vase'])),
                ('bedroom', json.dumps(['person', 'bed', 'book', 'clock', 'cell phone', 'teddy bear', 'laptop', 'remote', 'tv'])),
                ('kitchen', json.dumps(['person', 'bottle', 'cup', 'bowl', 'fork', 'knife', 'spoon', 'sink', 'oven', 'microwave', 'toaster', 'refrigerator', 'dining table', 'chair'])),
                ('office', json.dumps(['person', 'chair', 'laptop', 'keyboard', 'mouse', 'cell phone', 'book', 'clock', 'scissors', 'tv'])),
                ('street', json.dumps(['person', 'car', 'bus', 'truck', 'bicycle', 'motorcycle', 'traffic light', 'stop sign', 'fire hydrant', 'bench', 'dog'])),
                ('park', json.dumps(['person', 'bench', 'bird', 'dog', 'bicycle', 'frisbee', 'kite', 'potted plant'])),
            ]
            cursor.executemany('INSERT OR IGNORE INTO scene_context (scene_name, yolo_classes) VALUES (?, ?)', fallback_data)
            conn.commit()


    def get_context_for_scene(self, scene_name, vocabulary='coco80'):
        """
        Return the context (classes, model_file) for a given scene.
        Returns: {'classes': [...], 'model': 'filename.pt'}
        vocabulary: 'coco80' (default) or 'objects365'
        """
        table = self._get_table(vocabulary)
        simple_name = scene_name.split('/')[-1].replace('_', ' ')

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            def query(name):
                cursor.execute(f'SELECT yolo_classes, model_file FROM {table} WHERE scene_name = ?', (name,))
                return cursor.fetchone()

            row = query(scene_name)
            if not row:
                row = query(simple_name)
            if not row:
                cursor.execute(f'SELECT scene_name, yolo_classes, model_file FROM {table}')
                all_rows = cursor.fetchall()
                for db_scene, db_classes, db_model in all_rows:
                    if db_scene in scene_name or scene_name in db_scene:
                        return {'classes': json.loads(db_classes), 'model': db_model}
                return {'classes': ['person'], 'model': 'yolov8s-worldv2.pt'}

            return {'classes': json.loads(row[0]), 'model': row[1]}

    # Legacy support
    def get_classes_for_scene(self, scene_name, vocabulary='coco80'):
        return self.get_context_for_scene(scene_name, vocabulary)['classes']

    def update_scene(self, scene_name, classes_list, model_file=None, vocabulary='coco80'):
        """Add or update a mapping in the given vocabulary table."""
        table = self._get_table(vocabulary)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            classes_json = json.dumps(classes_list)

            if model_file:
                cursor.execute(f'''
                    INSERT INTO {table} (scene_name, yolo_classes, model_file)
                    VALUES (?, ?, ?)
                    ON CONFLICT(scene_name) DO UPDATE SET
                        yolo_classes=excluded.yolo_classes,
                        model_file=excluded.model_file
                ''', (scene_name, classes_json, model_file))
            else:
                cursor.execute(f'''
                    INSERT INTO {table} (scene_name, yolo_classes)
                    VALUES (?, ?)
                    ON CONFLICT(scene_name) DO UPDATE SET
                        yolo_classes=excluded.yolo_classes
                ''', (scene_name, classes_json))

            conn.commit()

    def get_all_scenes(self, vocabulary='coco80'):
        table = self._get_table(vocabulary)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f'SELECT scene_name, yolo_classes, model_file FROM {table} ORDER BY scene_name')
            return [
                {'name': r[0], 'classes': json.loads(r[1]), 'model': r[2]}
                for r in cursor.fetchall()
            ]
