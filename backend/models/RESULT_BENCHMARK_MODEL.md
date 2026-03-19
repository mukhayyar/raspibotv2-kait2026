(.venv) takanolab@raspberrypi:~/yahboom_control/PENS-KAIT 2026/backend/models $ uv run yo
lo detect predict model=yolo26n_saved_model/yolo26n_float32.tflite source='bus.jpg'
Ultralytics 8.4.14 🚀 Python-3.11.2 torch-2.10.0+cpu CPU (aarch64)
Loading yolo26n_saved_model/yolo26n_float32.tflite for TensorFlow Lite inference...
/home/takanolab/yahboom_control/PENS-KAIT 2026/backend/.venv/lib/python3.11/site-packages/tensorflow/lite/python/interpreter.py:457: UserWarning:     Warning: tf.lite.Interpreter is deprecated and is scheduled for deletion in
    TF 2.20. Please use the LiteRT interpreter from the ai_edge_litert package.
    See the [migration guide](https://ai.google.dev/edge/litert/migration)
    for details.
    
  warnings.warn(_INTERPRETER_DELETION_WARNING)
INFO: Created TensorFlow Lite XNNPACK delegate for CPU.

image 1/1 /home/takanolab/yahboom_control/PENS-KAIT 2026/backend/models/bus.jpg: 640x640 4 persons, 1 bus, 309.1ms
Speed: 11.3ms preprocess, 309.1ms inference, 0.5ms postprocess per image at shape (1, 3, 640, 640)
Results saved to /home/takanolab/yahboom_control/PENS-KAIT 2026/runs/detect/predict3
💡 Learn more at https://docs.ultralytics.com/modes/predict
VS Code: view Ultralytics VS Code Extension ⚡ at https://docs.ultralytics.com/integrations/vscode
(.venv) takanolab@raspberrypi:~/yahboom_control/PENS-KAIT 2026/backend/models $ uv run yolo detect predict model=yolo26n.onnx source='bus.jpg'
Ultralytics 8.4.14 🚀 Python-3.11.2 torch-2.10.0+cpu CPU (aarch64)
Loading yolo26n.onnx for ONNX Runtime inference...
2026-02-27 16:52:44.116120657 [W:onnxruntime:Default, device_discovery.cc:211 DiscoverDevicesForPlatform] GPU device discovery failed: device_discovery.cc:91 ReadFileContents Failed to open file: "/sys/class/drm/card1/device/vendor"
Using ONNX Runtime 1.24.1 with CPUExecutionProvider

image 1/1 /home/takanolab/yahboom_control/PENS-KAIT 2026/backend/models/bus.jpg: 640x640 4 persons, 1 bus, 420.3ms
Speed: 14.6ms preprocess, 420.3ms inference, 0.9ms postprocess per image at shape (1, 3, 640, 640)
Results saved to /home/takanolab/yahboom_control/PENS-KAIT 2026/runs/detect/predict4
💡 Learn more at https://docs.ultralytics.com/modes/predict
VS Code: view Ultralytics VS Code Extension ⚡ at https://docs.ultralytics.com/integrations/vscode
(.venv) takanolab@raspberrypi:~/yahboom_control/PENS-KAIT 2026/backend/models $ uv run yolo detect predict model=yolo26n.pt source='bus.jpg'
Ultralytics 8.4.14 🚀 Python-3.11.2 torch-2.10.0+cpu CPU (aarch64)
YOLO26n summary (fused): 122 layers, 2,408,932 parameters, 0 gradients, 5.4 GFLOPs

image 1/1 /home/takanolab/yahboom_control/PENS-KAIT 2026/backend/models/bus.jpg: 640x480 4 persons, 1 bus, 460.8ms
Speed: 9.9ms preprocess, 460.8ms inference, 1.0ms postprocess per image at shape (1, 3, 640, 480)
Results saved to /home/takanolab/yahboom_control/PENS-KAIT 2026/runs/detect/predict5
💡 Learn more at https://docs.ultralytics.com/modes/predict
VS Code: view Ultralytics VS Code Extension ⚡ at https://docs.ultralytics.com/integrations/vscode


(.venv) takanolab@raspberrypi:~/yahboom_control/PENS-KAIT 2026/backend/models $ uv run yolo detect predict model=yolo26n_saved_model/yolo26n_float16.tflite source='bus.jpg'
Ultralytics 8.4.14 🚀 Python-3.11.2 torch-2.10.0+cpu CPU (aarch64)
Loading yolo26n_saved_model/yolo26n_float16.tflite for TensorFlow Lite inference...
/home/takanolab/yahboom_control/PENS-KAIT 2026/backend/.venv/lib/python3.11/site-packages/tensorflow/lite/python/interpreter.py:457: UserWarning:     Warning: tf.lite.Interpreter is deprecated and is scheduled for deletion in
    TF 2.20. Please use the LiteRT interpreter from the ai_edge_litert package.
    See the [migration guide](https://ai.google.dev/edge/litert/migration)
    for details.
    
  warnings.warn(_INTERPRETER_DELETION_WARNING)
INFO: Created TensorFlow Lite XNNPACK delegate for CPU.

image 1/1 /home/takanolab/yahboom_control/PENS-KAIT 2026/backend/models/bus.jpg: 640x640 4 persons, 1 bus, 302.0ms
Speed: 9.2ms preprocess, 302.0ms inference, 0.9ms postprocess per image at shape (1, 3, 640, 640)
Results saved to /home/takanolab/yahboom_control/PENS-KAIT 2026/runs/detect/predict6
💡 Learn more at https://docs.ultralytics.com/modes/predict
VS Code: view Ultralytics VS Code Extension ⚡ at https://docs.ultralytics.com/integrations/vscode

