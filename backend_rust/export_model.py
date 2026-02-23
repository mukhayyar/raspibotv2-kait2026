
import os
import sys

# Ensure we can import ultralytics
try:
    from ultralytics import YOLO
except ImportError:
    print("Error: ultralytics not installed. Please run this in the correct environment.")
    sys.exit(1)

def export_model():
    model_path = "../backend/models/yolov8s-worldv2.pt"
    output_path = "../backend/models/yolov8s-worldv2.onnx"
    
    if not os.path.exists(model_path):
        print(f"Error: Model not found at {model_path}")
        # Try fallbacks
        model_path = "../backend/models/yolo26n.pt"
        if not os.path.exists(model_path):
            print("No models found in backend/models/")
            sys.exit(1)
            
    print(f"Exporting {model_path} to ONNX...")
    
    model = YOLO(model_path)
    # Export to ONNX with dynamic axes for batching if needed, but static is faster for single stream
    # imgSz = [320, 320] for performance matching our python script
    success = model.export(format="onnx", opset=12, imgsz=320, dynamic=False)
    
    print(f"Export completed: {success}")

if __name__ == "__main__":
    export_model()
