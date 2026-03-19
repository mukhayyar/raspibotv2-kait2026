#!/usr/bin/env python3
"""
build_context_objects365.py
────────────────────────────
Generate context_new.db — same 365 Places365 scenes as context.db,
but with class lists drawn from the Objects365 vocabulary (365 classes)
instead of the COCO-80 vocabulary.

Usage:
    python build_context_objects365.py              # writes context_new.db
    python build_context_objects365.py --out my.db  # custom output path
    python build_context_objects365.py --dry-run    # print mappings, no write
"""

import csv
import json
import os
import sqlite3
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH   = os.path.join(SCRIPT_DIR, 'Scene hierarchy - Places365.csv')

# ─────────────────────────────────────────────────────────────────────────────
# Official Objects365 v1 category names (365 classes, verified order)
# These are the class names the fine-tuned YOLOWorld model understands.
# ─────────────────────────────────────────────────────────────────────────────
OBJ365 = [
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
]

# Deduplicate while preserving order
_seen = set()
OBJ365_SET = []
for c in OBJ365:
    if c not in _seen:
        _seen.add(c)
        OBJ365_SET.append(c)
OBJ365_SET = set(OBJ365_SET)  # fast lookup

# ─────────────────────────────────────────────────────────────────────────────
# Level-2 category → Objects365 classes
# (same 16 columns as the Places365 CSV)
# ─────────────────────────────────────────────────────────────────────────────
CATEGORY_CLASSES = {
    # 0  shopping and dining
    0:  ['chair', 'stool', 'desk', 'plate', 'cup', 'wine glass', 'bottle',
         'bowl', 'fork', 'knife', 'spoon', 'tray', 'basket', 'bag',
         'handbag', 'cash register', 'bread', 'cake', 'pizza', 'hamburger',
         'hot dog', 'sandwich', 'donut', 'ice cream', 'sushi', 'noodles',
         'rice', 'juice', 'coffee', 'tea', 'beer', 'wine', 'cocktail',
         'storage box', 'canned food', 'cookies'],
    # 1  workplace (office, factory, lab)
    1:  ['chair', 'desk', 'laptop', 'keyboard', 'monitor', 'tablet',
         'printer', 'router', 'book', 'notebook', 'folder', 'pen',
         'scissors', 'ruler', 'stapler', 'eraser', 'pencil case',
         'marker', 'clock', 'cell phone', 'magazine', 'whiteboard',
         'blackboard', 'projector', 'speaker', 'headphones', 'cabinet'],
    # 2  home or hotel
    2:  ['chair', 'couch', 'bed', 'pillow', 'blanket', 'mattress',
         'curtain', 'mirror', 'rug', 'carpet', 'tv', 'remote control',
         'clock', 'vase', 'potted plant', 'book', 'cup', 'bottle',
         'lamp', 'shelf', 'drawer', 'wardrobe', 'cabinet', 'stool',
         'picture frame', 'candle', 'fan', 'air conditioner'],
    # 3  transportation (interiors, stations)
    3:  ['suitcase', 'backpack', 'handbag', 'bench', 'cell phone',
         'umbrella', 'book', 'notebook', 'bag', 'clock', 'tv',
         'headphones', 'luggage', 'ticket'],
    # 4  sports and leisure
    4:  ['soccer ball', 'basketball', 'volleyball', 'tennis racket',
         'baseball', 'football', 'rugby ball', 'skateboard', 'surfboard',
         'skis', 'frisbee', 'kite', 'golf club', 'golf ball',
         'boxing gloves', 'bench', 'trophy', 'medal', 'backpack',
         'bottle', 'towel', 'fishing rod', 'bicycle'],
    # 5  cultural (art, education, religion, military)
    5:  ['book', 'notebook', 'pen', 'clock', 'vase', 'chair', 'stool',
         'potted plant', 'backpack', 'flag', 'statue', 'painting',
         'picture frame', 'lantern', 'candle', 'whiteboard', 'blackboard'],
    # 6  water, ice, snow
    6:  ['boat', 'surfboard', 'umbrella', 'skis', 'bird', 'fishing rod',
         'backpack', 'life preserver'],
    # 7  mountains, hills, desert, sky
    7:  ['backpack', 'bottle', 'bird', 'eagle', 'owl', 'map', 'binoculars',
         'tent', 'flag'],
    # 8  forest, field, jungle
    8:  ['bird', 'dog', 'cat', 'horse', 'cow', 'sheep', 'pig', 'rabbit',
         'frog', 'eagle', 'owl', 'backpack', 'bottle', 'basket', 'bicycle'],
    # 9  man-made elements
    9:  ['bench', 'clock', 'potted plant', 'fire hydrant', 'traffic light',
         'street lights', 'traffic cone', 'road sign', 'stop sign',
         'parking meter', 'mailbox', 'trash can', 'fountain', 'statue'],
    # 10 transportation (roads, airports, bridges)
    10: ['car', 'suv', 'van', 'bus', 'truck', 'motorcycle', 'bicycle',
         'traffic light', 'stop sign', 'parking meter', 'airplane',
         'boat', 'train', 'road sign', 'traffic cone', 'helmet'],
    # 11 cultural or historical building
    11: ['bench', 'clock', 'vase', 'potted plant', 'book', 'flag',
         'statue', 'lantern', 'candle', 'picture frame', 'fountain'],
    # 12 sports fields, parks, leisure spaces
    12: ['bench', 'bicycle', 'dog', 'bird', 'frisbee', 'kite',
         'soccer ball', 'basketball', 'volleyball', 'skateboard',
         'backpack', 'bottle', 'umbrella', 'potted plant', 'trash can'],
    # 13 industrial and construction
    13: ['truck', 'van', 'machinery vehicle', 'car', 'backpack',
         'hammer', 'wrench', 'drill', 'saw', 'helmet', 'storage box',
         'barrel', 'ladder'],
    # 14 houses, cabins, gardens, farms
    14: ['horse', 'sheep', 'cow', 'dog', 'cat', 'bird', 'pig', 'duck',
         'rabbit', 'potted plant', 'bench', 'bicycle', 'basket',
         'flower', 'vase', 'watering can'],
    # 15 commercial buildings, shops, cities
    15: ['car', 'suv', 'van', 'bus', 'truck', 'motorcycle', 'bicycle',
         'handbag', 'backpack', 'umbrella', 'bench', 'traffic light',
         'cell phone', 'bottle', 'bag', 'street lights', 'trash can',
         'traffic cone', 'stop sign'],
}

# ─────────────────────────────────────────────────────────────────────────────
# Scene-name keyword → Objects365 classes
# ─────────────────────────────────────────────────────────────────────────────
KEYWORD_CLASSES = {
    # ── Food & drink ──────────────────────────────────────────────────────────
    'kitchen':      ['microwave', 'toaster', 'refrigerator', 'oven', 'sink',
                     'faucet', 'kettle', 'blender', 'gas stove', 'cutting board',
                     'bowl', 'cup', 'bottle', 'plate', 'fork', 'knife', 'spoon',
                     'pot', 'pots', 'tray', 'chair', 'stool', 'desk'],
    'dining':       ['desk', 'chair', 'fork', 'knife', 'spoon', 'bowl',
                     'cup', 'wine glass', 'bottle', 'plate', 'vase', 'candle'],
    'restaurant':   ['chair', 'stool', 'desk', 'fork', 'knife', 'spoon',
                     'bowl', 'cup', 'wine glass', 'bottle', 'plate', 'tray',
                     'vase', 'candle', 'menu'],
    'cafeteria':    ['chair', 'stool', 'desk', 'cup', 'bowl', 'bottle',
                     'fork', 'knife', 'spoon', 'tray', 'bread', 'cake'],
    'bar':          ['bottle', 'wine glass', 'cup', 'chair', 'stool', 'tv',
                     'beer', 'cocktail', 'candle'],
    'pub':          ['bottle', 'wine glass', 'cup', 'beer', 'chair', 'tv'],
    'bakery':       ['cake', 'donut', 'bread', 'cookies', 'bottle',
                     'bowl', 'tray', 'basket'],
    'pizzeria':     ['pizza', 'bottle', 'cup', 'chair', 'fork', 'knife'],
    'deli':         ['sandwich', 'bread', 'bottle', 'bowl', 'tray'],
    'supermarket':  ['bottle', 'banana', 'apple', 'orange', 'broccoli',
                     'carrot', 'cake', 'basket', 'bag', 'canned food',
                     'pineapple', 'watermelon', 'bread', 'cookies'],
    'market':       ['bottle', 'banana', 'apple', 'orange', 'umbrella',
                     'handbag', 'backpack', 'basket', 'flower', 'vase'],
    'grocery':      ['bottle', 'banana', 'apple', 'orange', 'broccoli',
                     'carrot', 'pineapple', 'basket', 'bag'],
    'food':         ['bowl', 'cup', 'bottle', 'fork', 'knife', 'spoon',
                     'banana', 'apple', 'sandwich', 'orange', 'pizza',
                     'cake', 'donut', 'bread', 'hamburger', 'hot dog'],
    # ── Home rooms ────────────────────────────────────────────────────────────
    'bedroom':      ['bed', 'pillow', 'blanket', 'mattress', 'clock',
                     'book', 'cell phone', 'stuffed animal', 'lamp',
                     'laptop', 'remote control', 'tv', 'curtain', 'mirror',
                     'wardrobe', 'drawer'],
    'dorm':         ['bed', 'chair', 'laptop', 'book', 'cell phone',
                     'clock', 'backpack', 'mirror', 'lamp'],
    'nursery':      ['bed', 'stuffed animal', 'book', 'clock', 'chair',
                     'pillow', 'blanket'],
    'living_room':  ['couch', 'chair', 'tv', 'remote control', 'potted plant',
                     'book', 'clock', 'vase', 'cat', 'dog', 'carpet',
                     'lamp', 'pillow', 'blanket', 'curtain', 'magazine'],
    'lounge':       ['couch', 'chair', 'tv', 'remote control', 'bottle',
                     'cup', 'clock', 'lamp', 'potted plant'],
    'lobby':        ['couch', 'chair', 'potted plant', 'suitcase', 'clock',
                     'vase', 'lamp', 'mirror', 'statue'],
    'waiting_room': ['chair', 'bench', 'book', 'magazine', 'cell phone',
                     'clock', 'tv', 'backpack', 'bag'],
    'bathroom':     ['toilet', 'sink', 'faucet', 'bathtub', 'shower',
                     'toothbrush', 'toothpaste', 'razor', 'shampoo',
                     'soap', 'mirror', 'towel', 'bottle', 'cup', 'comb'],
    'laundry':      ['bottle', 'washing machine', 'basket', 'detergent'],
    # ── Office & work ─────────────────────────────────────────────────────────
    'office':       ['chair', 'laptop', 'keyboard', 'monitor', 'tablet',
                     'book', 'notebook', 'folder', 'pen', 'cell phone',
                     'scissors', 'clock', 'tv', 'printer', 'speaker',
                     'whiteboard', 'ruler', 'stapler'],
    'computer':     ['laptop', 'keyboard', 'monitor', 'tablet', 'chair',
                     'cell phone', 'tv', 'speaker', 'headphones'],
    'conference':   ['chair', 'laptop', 'tv', 'projector', 'bottle', 'cup',
                     'cell phone', 'clock', 'book', 'whiteboard', 'marker'],
    'classroom':    ['chair', 'book', 'notebook', 'pen', 'laptop', 'backpack',
                     'clock', 'tv', 'whiteboard', 'blackboard', 'ruler',
                     'marker', 'eraser'],
    'lecture':      ['chair', 'laptop', 'book', 'backpack', 'clock',
                     'projector', 'whiteboard', 'blackboard', 'microphone'],
    'library':      ['book', 'notebook', 'magazine', 'newspaper', 'chair',
                     'laptop', 'backpack', 'clock', 'lamp', 'shelf'],
    'studio':       ['chair', 'laptop', 'keyboard', 'monitor', 'book',
                     'cell phone', 'scissors', 'tv', 'camera', 'tripod',
                     'microphone', 'speaker', 'headphones'],
    'lab':          ['laptop', 'keyboard', 'monitor', 'chair', 'bottle',
                     'book', 'clock', 'cell phone', 'stethoscope',
                     'syringe', 'thermometer', 'microscope'],
    # ── Transport ─────────────────────────────────────────────────────────────
    'parking':      ['car', 'suv', 'van', 'truck', 'motorcycle', 'bicycle',
                     'traffic light', 'stop sign', 'parking meter',
                     'traffic cone', 'road sign'],
    'garage':       ['car', 'suv', 'van', 'truck', 'motorcycle', 'bicycle',
                     'hammer', 'wrench', 'drill'],
    'highway':      ['car', 'suv', 'van', 'bus', 'truck', 'motorcycle',
                     'traffic light', 'road sign', 'traffic cone'],
    'street':       ['car', 'suv', 'van', 'bus', 'truck', 'bicycle',
                     'motorcycle', 'traffic light', 'stop sign',
                     'fire hydrant', 'bench', 'dog', 'street lights',
                     'trash can', 'traffic cone', 'mailbox', 'umbrella'],
    'road':         ['car', 'suv', 'bus', 'truck', 'motorcycle', 'bicycle',
                     'traffic light', 'stop sign', 'road sign', 'traffic cone'],
    'crosswalk':    ['car', 'bus', 'traffic light', 'bicycle', 'stop sign'],
    'intersection': ['car', 'suv', 'bus', 'truck', 'traffic light',
                     'stop sign', 'bicycle', 'road sign'],
    'bridge':       ['car', 'bus', 'truck', 'boat', 'bicycle'],
    'driveway':     ['car', 'suv', 'truck', 'bicycle', 'motorcycle'],
    'airport':      ['airplane', 'suitcase', 'backpack', 'handbag', 'bench',
                     'cell phone', 'tv', 'umbrella', 'bag', 'clock'],
    'airfield':     ['airplane', 'suv', 'van', 'truck'],
    'runway':       ['airplane'],
    'hangar':       ['airplane', 'truck', 'machinery vehicle'],
    'train':        ['train', 'suitcase', 'backpack', 'bench', 'bag'],
    'subway':       ['train', 'bench', 'backpack', 'cell phone', 'bag'],
    'bus_stop':     ['bus', 'bench', 'backpack', 'umbrella', 'bag'],
    'harbor':       ['boat', 'truck', 'barrel', 'rope'],
    'marina':       ['boat', 'life preserver'],
    'dock':         ['boat', 'barrel', 'rope'],
    'pier':         ['boat', 'bench', 'bird', 'fishing rod'],
    # ── Sports ────────────────────────────────────────────────────────────────
    'swimming':     ['bench', 'towel', 'bottle', 'umbrella'],
    'pool':         ['bench', 'umbrella', 'chair', 'towel', 'bottle'],
    'gym':          ['bench', 'backpack', 'bottle', 'towel', 'trophy',
                     'basketball', 'volleyball', 'soccer ball'],
    'tennis':       ['tennis racket', 'soccer ball', 'bench', 'backpack',
                     'bottle', 'towel'],
    'basketball':   ['basketball', 'bench', 'backpack', 'bottle'],
    'baseball':     ['baseball', 'bench', 'backpack', 'helmet', 'gloves'],
    'soccer':       ['soccer ball', 'bench', 'backpack', 'bottle'],
    'football':     ['football', 'rugby ball', 'bench', 'helmet'],
    'ski':          ['skis', 'helmet', 'gloves', 'backpack', 'goggles'],
    'ice':          ['skis', 'helmet', 'gloves'],
    'stadium':      ['soccer ball', 'basketball', 'bench', 'backpack',
                     'bottle', 'trophy', 'flag', 'speaker'],
    'arena':        ['bench', 'chair', 'backpack', 'flag', 'trophy',
                     'microphone', 'speaker'],
    'playground':   ['bench', 'bicycle', 'dog', 'skateboard', 'basketball',
                     'kite', 'frisbee', 'balloon'],
    'park':         ['bench', 'bird', 'dog', 'bicycle', 'frisbee', 'kite',
                     'potted plant', 'flower', 'umbrella', 'trash can'],
    # ── Nature & outdoors ─────────────────────────────────────────────────────
    'garden':       ['bench', 'bird', 'potted plant', 'dog', 'cat', 'vase',
                     'flower', 'basket', 'watering can'],
    'yard':         ['bench', 'dog', 'cat', 'bird', 'bicycle', 'potted plant',
                     'basket', 'flower'],
    'patio':        ['chair', 'bench', 'potted plant', 'umbrella', 'dog',
                     'cat', 'bottle', 'vase', 'flower'],
    'balcony':      ['chair', 'potted plant', 'umbrella', 'bicycle', 'flower'],
    'zoo':          ['elephant', 'camel', 'zebra', 'polar bear', 'koala',
                     'seal', 'giraffe', 'bird', 'eagle', 'owl',
                     'bench', 'backpack', 'bottle'],
    'farm':         ['horse', 'sheep', 'cow', 'pig', 'dog', 'cat', 'bird',
                     'duck', 'rabbit', 'truck', 'basket', 'shovel'],
    'stable':       ['horse', 'dog', 'basket', 'saddle'],
    'kennel':       ['dog', 'cat', 'rabbit'],
    'pasture':      ['horse', 'sheep', 'cow', 'dog', 'bird', 'duck'],
    'forest':       ['bird', 'dog', 'eagle', 'owl', 'backpack', 'bottle',
                     'mushroom', 'basket'],
    'field':        ['bird', 'dog', 'cow', 'horse', 'sheep', 'bicycle',
                     'backpack'],
    'mountain':     ['backpack', 'bottle', 'map', 'binoculars', 'bird',
                     'eagle', 'flag'],
    'beach':        ['umbrella', 'surfboard', 'boat', 'bird', 'dog',
                     'frisbee', 'kite', 'towel', 'backpack', 'bottle',
                     'sandals', 'sunscreen'],
    'ocean':        ['boat', 'surfboard', 'bird', 'umbrella', 'fish'],
    'lake':         ['boat', 'bird', 'fishing rod', 'duck'],
    'river':        ['boat', 'bird', 'fishing rod', 'duck'],
    # ── Shopping & commercial ─────────────────────────────────────────────────
    'shop':         ['bottle', 'handbag', 'backpack', 'cell phone',
                     'umbrella', 'bag', 'basket', 'watch', 'glasses'],
    'store':        ['bottle', 'handbag', 'backpack', 'cell phone',
                     'bag', 'shelf', 'storage box'],
    'mall':         ['handbag', 'backpack', 'cell phone', 'umbrella',
                     'bench', 'potted plant', 'bag', 'watch', 'glasses'],
    'clothing':     ['handbag', 'backpack', 'belt', 'tie', 'hat', 'glasses',
                     'watch', 'boots', 'sneakers', 'high heels', 'sandals',
                     'slippers', 'gloves', 'scarf', 'suit'],
    'jewelry':      ['necklace', 'bracelet', 'ring', 'watch', 'glasses'],
    'toy':          ['stuffed animal', 'bicycle', 'skateboard', 'book',
                     'basketball', 'soccer ball', 'balloon'],
    # ── Hospitality & health ──────────────────────────────────────────────────
    'hotel':        ['bed', 'chair', 'couch', 'tv', 'remote control',
                     'suitcase', 'clock', 'vase', 'potted plant', 'lamp',
                     'pillow', 'blanket', 'mirror', 'curtain'],
    'hospital':     ['bed', 'chair', 'tv', 'clock', 'bottle', 'cell phone',
                     'wheelchair', 'crutch', 'stethoscope', 'syringe',
                     'thermometer', 'bandage', 'medicine', 'pillow'],
    'clinic':       ['chair', 'tv', 'clock', 'bottle', 'stethoscope',
                     'syringe', 'thermometer', 'bandage', 'medicine'],
    'pharmacy':     ['bottle', 'medicine', 'bandage'],
    'dentist':      ['chair', 'tv', 'medicine'],
    # ── Culture & religion ────────────────────────────────────────────────────
    'church':       ['bench', 'book', 'clock', 'vase', 'candle',
                     'flower', 'flag', 'lantern'],
    'temple':       ['bench', 'vase', 'potted plant', 'lantern',
                     'candle', 'statue', 'flower', 'incense'],
    'mosque':       ['clock', 'vase', 'book', 'lantern', 'candle'],
    'museum':       ['bench', 'vase', 'clock', 'book', 'potted plant',
                     'statue', 'picture frame', 'flag'],
    'gallery':      ['vase', 'bench', 'potted plant', 'picture frame',
                     'statue', 'painting'],
    'theater':      ['chair', 'microphone', 'speaker', 'camera', 'curtain'],
    'cinema':       ['chair', 'tv', 'cup', 'bottle', 'projector'],
    'casino':       ['chair', 'cup', 'bottle', 'tv', 'card'],
    'banquet':      ['chair', 'fork', 'knife', 'spoon', 'vase',
                     'wine glass', 'bottle', 'cup', 'candle', 'flower'],
    'ballroom':     ['chair', 'clock', 'vase', 'lamp', 'microphone',
                     'speaker', 'flower'],
    # ── Interior navigation ───────────────────────────────────────────────────
    'corridor':     ['fire hydrant', 'clock', 'potted plant', 'trash can',
                     'street lights'],
    'hallway':      ['clock', 'potted plant', 'vase', 'lamp', 'mirror'],
    'staircase':    ['backpack', 'handbag', 'trash can'],
    'elevator':     ['cell phone', 'backpack', 'mirror'],
    'closet':       ['handbag', 'backpack', 'umbrella', 'tie', 'belt',
                     'boots', 'sneakers', 'high heels', 'suit'],
    'attic':        ['suitcase', 'book', 'clock', 'stuffed animal', 'box'],
    'basement':     ['bicycle', 'suitcase', 'bottle', 'barrel', 'storage box'],
    # ── Accommodation ─────────────────────────────────────────────────────────
    'cabin':        ['bed', 'chair', 'book', 'clock', 'cup', 'lamp',
                     'blanket', 'pillow'],
    'cottage':      ['chair', 'potted plant', 'dog', 'cat', 'bed',
                     'flower', 'vase'],
    'veranda':      ['chair', 'bench', 'potted plant', 'dog', 'cat',
                     'flower', 'umbrella'],
    # ── Education ─────────────────────────────────────────────────────────────
    'kindergarten': ['chair', 'book', 'stuffed animal', 'backpack', 'clock',
                     'balloon', 'crayon', 'pencil case'],
    'playroom':     ['stuffed animal', 'book', 'tv', 'chair', 'balloon',
                     'basketball', 'soccer ball'],
    # ── Industrial ────────────────────────────────────────────────────────────
    'construction': ['truck', 'machinery vehicle', 'hammer', 'wrench',
                     'drill', 'saw', 'helmet', 'barrel', 'ladder',
                     'storage box', 'traffic cone'],
    'factory':      ['truck', 'machinery vehicle', 'chair', 'helmet',
                     'storage box', 'barrel'],
    'warehouse':    ['truck', 'bicycle', 'storage box', 'barrel', 'ladder',
                     'shelf', 'forklift'],
    # ── Vehicles (as scene interiors) ─────────────────────────────────────────
    'cockpit':      ['airplane'],
    'cabin_plane':  ['airplane', 'backpack', 'suitcase', 'seat belt'],
    'boat_int':     ['boat', 'life preserver', 'rope'],
    # ── Music & performance ───────────────────────────────────────────────────
    'concert':      ['guitar', 'violin', 'piano', 'drum', 'trumpet',
                     'saxophone', 'microphone', 'speaker', 'headphones',
                     'bench', 'flag'],
    'music':        ['guitar', 'violin', 'piano', 'drum', 'trumpet',
                     'saxophone', 'harmonica', 'ukulele', 'microphone',
                     'speaker', 'headphones'],
    # ── Art & craft ───────────────────────────────────────────────────────────
    'art':          ['paintbrush', 'palette', 'vase', 'statue', 'picture frame',
                     'scissors', 'pen', 'ruler', 'marker'],
    'craft':        ['scissors', 'pen', 'ruler', 'tape', 'marker',
                     'paintbrush', 'palette'],
}


def get_classes(scene_name: str, category_flags: list) -> list:
    """Build Objects365 class list from CSV category flags + scene name keywords."""
    classes = {'person'}

    # 1. Category-flag based
    for idx, flag in enumerate(category_flags):
        if flag == 1 and idx in CATEGORY_CLASSES:
            classes.update(CATEGORY_CLASSES[idx])

    # 2. Keyword based (word-boundary safe)
    scene_lower  = scene_name.lower()
    scene_words  = set(scene_lower.split('_'))
    for keyword, kw_classes in KEYWORD_CLASSES.items():
        if keyword in scene_words or ('_' in keyword and keyword in scene_lower):
            classes.update(kw_classes)

    # 3. Validate against Objects365 set
    return sorted(c for c in classes if c in OBJ365_SET)


def build(out_path: str, dry_run: bool = False):
    rows = []

    with open(CSV_PATH, encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)   # Level 1 header
        next(reader)   # Level 2 header

        for row in reader:
            if not row or len(row) < 4:
                continue
            raw = row[0].strip().strip("'\"")
            if not raw or raw == 'category':
                continue

            parts = [p for p in raw.split('/') if p and len(p) > 1]
            scene_name = '_'.join(parts)

            flags = []
            for i in range(4, min(20, len(row))):
                try:
                    flags.append(int(row[i]))
                except (ValueError, IndexError):
                    flags.append(0)

            classes = get_classes(scene_name, flags)
            rows.append((scene_name, classes))

    if dry_run:
        for name, cls in rows:
            print(f'{name:40s} ({len(cls):3d} classes)  {cls[:6]}...')
        print(f'\nTotal: {len(rows)} scenes')
        zero_class = [n for n, c in rows if len(c) <= 1]
        print(f'Scenes with <=1 class: {len(zero_class)}')
        if zero_class:
            print(zero_class)
        return

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    conn = sqlite3.connect(out_path)
    cur  = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS scene_context (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_name TEXT    UNIQUE NOT NULL,
            yolo_classes TEXT  NOT NULL,
            model_file TEXT    DEFAULT 'yolov8s-worldv2.pt'
        )
    ''')
    cur.execute('DELETE FROM scene_context')

    cur.executemany(
        'INSERT INTO scene_context (scene_name, yolo_classes) VALUES (?, ?)',
        [(name, json.dumps(cls)) for name, cls in rows]
    )
    conn.commit()

    # Summary
    cur.execute('SELECT COUNT(*) FROM scene_context')
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM scene_context WHERE json_array_length(yolo_classes) <= 1")
    lean  = cur.fetchone()[0]
    conn.close()

    print(f'Wrote {total} scenes → {out_path}')
    print(f'Scenes with <=1 class: {lean}  (should be 0)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build context_new.db with Objects365 classes')
    parser.add_argument('--out',     default=os.path.join(SCRIPT_DIR, 'context_new.db'),
                        help='Output SQLite database path')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print mappings without writing the database')
    args = parser.parse_args()
    build(args.out, dry_run=args.dry_run)
