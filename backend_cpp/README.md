# PENS-KAIT 2026 - C++ High Performance Backend

This directory contains the experimental C++ backend designed to replace the Python Flask application for high-performance scenarios.

## Goals
- **Low Latency**: Minimize inference and control loop processing time.
- **High FPS**: Target 30fps+ for Object Detection using ONNX Runtime (CPU/GPU).
- **Concurrency**: separate threads for Camera, Inference, and Robot Control.

## Key Libraries
- **OpenCV C++**: For image acquisition and pre-processing.
- **ONNX Runtime**: For executing YOLO weights exported to `.onnx`.
- **WiringPi / Pigpio** (TBD): For I2C/GPIO communication with the Raspbot Hat.
- **drogon** or **uWebSockets**: For C++ WebSocket server (to communicate with the Frontend).

## Build
```bash
mkdir build && cd build
cmake ..
make
./robot_core
```

## Roadmap
1. [ ] Port Camera Capture loop.
2. [ ] Integrate ONNX Runtime for YOLO.
3. [ ] Implement WebSocket server for Frontend communication.
4. [ ] Port Raspbot_Lib (I2C protocols) to C++.
