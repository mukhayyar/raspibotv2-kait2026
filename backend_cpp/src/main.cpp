#include <iostream>
#include <opencv2/opencv.hpp>
// #include <onnxruntime_cxx_api.h> // Uncomment when available

int main() {
    std::cout << "[INFO] Starting PENS-KAIT 2026 C++ Backend..." << std::endl;

    // Check OpenCV
    std::cout << "[INFO] OpenCV Version: " << CV_VERSION << std::endl;

    try {
        // TODO: Initialize Raspbot Serial/I2C here
        
        // TODO: Load ONNX Models
        // Ort::Env env(ORT_LOGGING_LEVEL_WARNING, "RobotAI");
        
        // Camera Loop
        cv::VideoCapture cap(0);
        if (!cap.isOpened()) {
            std::cerr << "[ERROR] Could not open camera" << std::endl;
            // return -1; // Don't exit yet during dev
        }

        std::cout << "[INFO] Backend Core Initialized. Waiting for tasks..." << std::endl;

        cv::Mat frame;
        while (true) {
            // Placeholder loop
            // cap >> frame;
            // if (frame.empty()) break;
            
            // Inference...

            // WebSocket broadcast...
            
            // cv::imshow("Debug", frame);
            // if (cv::waitKey(1) == 27) break;
            break; // Exit immediately for now
        }

    } catch (const std::exception& e) {
        std::cerr << "[ERROR] Exception: " << e.what() << std::endl;
        return 1;
    }

    return 0;
}
