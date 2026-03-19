from ultralytics import YOLO

# Load the exported NCNN model
ncnn_model = YOLO("./models/yolov8s-worldv2_ncnn_model")

# Run inference with Vulkan GPU acceleration (first Vulkan device)
results = ncnn_model("https://ultralytics.com/images/bus.jpg", device="vulkan:0")

# Use second Vulkan device in multi-GPU systems
results = ncnn_model("https://ultralytics.com/images/bus.jpg", device="vulkan:1")