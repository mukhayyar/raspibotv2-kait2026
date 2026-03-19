import argparse
from ultralytics import YOLO

def export_model():
    parser = argparse.ArgumentParser(description="Export YOLO model to a specified format.")
    parser.add_argument("--model", type=str, default="yolo26n.pt", help="Path to the YOLO model (.pt file)")
    parser.add_argument("--format", type=str, default="onnx", help="Target format (e.g., onnx, openvino, engine, tflite, etc.)")
    
    args = parser.parse_args()
    
    try:
        model = YOLO(args.model)
        model.export(format=args.format)
        print(f"Model exported successfully to {args.format} format.")
    except Exception as e:
        print(f"Failed to export model: {e}")

if __name__ == "__main__":
    export_model()