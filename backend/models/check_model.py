from ultralytics import YOLO

# Load your model
model = YOLO('Phase2/yolov8s-worldv2.pt')  # Replace with your .pt file path

# Print the classes
print(model.names)