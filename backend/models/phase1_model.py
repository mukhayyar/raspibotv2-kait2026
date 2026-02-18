import cv2
import numpy as np
import os
import csv

class Phase1Model:
    def __init__(self, base_path):
        """
        Initialize the Caffe model for Places365.
        base_path: path to the 'backend' directory.
        """
        self.base_path = base_path
        self.prototxt = os.path.join(base_path, 'models/Phase1/deploy_googlenet_places365.prototxt')
        self.caffemodel = os.path.join(base_path, 'models/Phase1/googlenet_places365.caffemodel')
        self.labels_path = os.path.join(base_path, 'data/places365.csv')
        self.net = None
        self.labels = []
        
        self.load_labels()
        self.load_model()

    def load_labels(self):
        try:
            with open(self.labels_path, 'r') as f:
                # The csv has headers: category
                # Data lines like: /a/airfield
                # We want a list of class names accessibly by index 0..364
                reader = csv.reader(f)
                next(reader, None) # skip header
                self.labels = []
                for row in reader:
                   if row:
                       # format is '/a/airfield', we want 'airfield' or the full string
                       # The Caffe model output index corresponds to the line number (0-indexed after header)
                       self.labels.append(row[0])
            print(f"[Phase1] Loaded {len(self.labels)} labels.")
        except Exception as e:
            print(f"[ERROR] Failed to load Places365 labels: {e}")

    def load_model(self):
        try:
            if not os.path.exists(self.prototxt) or not os.path.exists(self.caffemodel):
                print(f"[WARN] Phase 1 model files not found at {self.prototxt} / {self.caffemodel}")
                return
            
            self.net = cv2.dnn.readNetFromCaffe(self.prototxt, self.caffemodel)
            # Force CPU for now to avoid CUDA errors with standard opencv-python
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            print("[Phase1] Caffe model loaded (CPU).")
                
        except Exception as e:
            print(f"[ERROR] Failed to load Phase 1 model: {e}")

    def predict(self, frame):
        """
        Run inference on a BGR image frame.
        Returns: list of (score, label) tuples.
        """
        if self.net is None:
            return []

        try:
            # GoogLeNet Places365 expects 224x224, mean (104, 117, 123)
            blob = cv2.dnn.blobFromImage(frame, 1.0, (224, 224), (104, 117, 123), False, False)
            self.net.setInput(blob)
            prob = self.net.forward()

            # prob is [[score0, score1, ...]]
            # Get top 5
            idxs = np.argsort(prob[0])[::-1][:5]
            
            results = []
            for i in idxs:
                label = self.labels[i] if i < len(self.labels) else f"Class {i}"
                score = float(prob[0][i])
                results.append((score, label))
                
            return results

        except Exception as e:
            print(f"[ERROR] Phase 1 inference failed: {e}")
            return []
