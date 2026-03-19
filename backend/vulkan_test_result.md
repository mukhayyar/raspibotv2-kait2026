(.venv) username@raspberrypi:~/.../.../backend $ uv run python vulkan_test.py 
WARNING ⚠️ Unable to automatically guess model task, assuming 'task=detect'. Explicitly define task for your model, i.e. 'task=detect', 'segment', 'classify','pose' or 'obb'.
Loading ./models/yolov8s-worldv2_ncnn_model for NCNN inference...
[0 V3D 7.1.10.2]  queueC=0[1]  queueT=0[1]
[0 V3D 7.1.10.2]  fp16-p/s/u/a=1/1/1/0  int8-p/s/u/a=1/1/1/0  bf16-p/s=1/0
[0 V3D 7.1.10.2]  subgroup=16(16~16)  ops=1/1/0/1/1/1/0/1/0/0
[0 V3D 7.1.10.2]  fp16-cm=0  int8-cm=0  bf16-cm=0  fp8-cm=0
[1 llvmpipe (LLVM 15.0.6, 128 bits)]  queueC=0[1]  queueT=0[1]
[1 llvmpipe (LLVM 15.0.6, 128 bits)]  fp16-p/s/u/a=1/1/1/1  int8-p/s/u/a=1/1/1/1  bf16-p/s=1/0
[1 llvmpipe (LLVM 15.0.6, 128 bits)]  subgroup=4(4~4)  ops=1/1/1/1/1/1/0/1/0/0
[1 llvmpipe (LLVM 15.0.6, 128 bits)]  fp16-cm=0  int8-cm=0  bf16-cm=0  fp8-cm=0

Downloading https://ultralytics.com/images/bus.jpg to 'bus.jpg': 48% ━━━━━╸────── 64.0/13
Downloading https://ultralytics.com/images/bus.jpg to 'bus.jpg': 100% ━━━━━━━━━━━━ 134.2KB 769.1KB/s 0.2s
image 1/1 /home/takanolab/yahboom_control/PENS-KAIT 2026/backend/bus.jpg: 640x640 4 persons, 1 bus, 15413.8ms
Speed: 19.5ms preprocess, 15413.8ms inference, 21.4ms postprocess per image at shape (1, 3, 640, 640)
Loading ./models/yolov8s-worldv2_ncnn_model for NCNN inference...

Found https://ultralytics.com/images/bus.jpg locally at bus.jpg
image 1/1 /home/takanolab/yahboom_control/PENS-KAIT 2026/backend/bus.jpg: 640x640 4 persons, 1 bus, 46782.5ms
Speed: 7.3ms preprocess, 46782.5ms inference, 5.5ms postprocess per image at shape (1, 3, 640, 640)