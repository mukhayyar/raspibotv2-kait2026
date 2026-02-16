from ultralytics import YOLO
model = YOLO('yolo26n.pt')  # Load model
model.export(format='onnx')  # Export to ONNX
