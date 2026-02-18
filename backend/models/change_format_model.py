from ultralytics import YOLO
model = YOLO('Phase2/yolo26n.pt')  # Load model
model.export(format='onnx')  # Export to ONNX
