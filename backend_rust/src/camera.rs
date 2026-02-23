use opencv::{
    core,
    prelude::*,
    videoio,
};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

pub struct FrameManager {
    raw_frame: Arc<Mutex<Option<core::Mat>>>,
}

impl FrameManager {
    pub fn new() -> Self {
        Self {
            raw_frame: Arc::new(Mutex::new(None)),
        }
    }

    pub fn update(&self, frame: core::Mat) {
        if let Ok(mut locked_frame) = self.raw_frame.lock() {
            *locked_frame = Some(frame);
        }
    }

    pub fn get(&self) -> Option<core::Mat> {
        if let Ok(locked_frame) = self.raw_frame.lock() {
            if let Some(ref frame) = *locked_frame {
                // Return a clone (deep copy) of the matrix
                return Some(frame.clone());
            }
        }
        None
    }
}

pub fn start_camera_thread() -> Arc<FrameManager> {
    let frame_manager = Arc::new(FrameManager::new());
    let fm_clone = Arc::clone(&frame_manager);

    thread::spawn(move || {
        println!("[INFO] Starting Rust camera capture thread...");

        // Try GStreamer pipeline for CSI camera
        let gst_pipeline = "libcamerasrc ! video/x-raw, width=640, height=480, framerate=30/1 ! videoconvert ! appsink";
        let mut cap = match videoio::VideoCapture::from_file(gst_pipeline, videoio::CAP_GSTREAMER) {
            Ok(c) => {
                if opencv::videoio::VideoCapture::is_opened(&c).unwrap_or(false) {
                    println!("[OK] Opened CSI Camera via GStreamer");
                    c
                } else {
                    println!("[WARN] GStreamer failed, falling back to V4L2 /dev/video0");
                    let mut fallback = videoio::VideoCapture::new(0, videoio::CAP_V4L2).unwrap();
                    let _ = fallback.set(videoio::CAP_PROP_FRAME_WIDTH, 640.0);
                    let _ = fallback.set(videoio::CAP_PROP_FRAME_HEIGHT, 480.0);
                    fallback
                }
            },
            Err(_) => {
                println!("[WARN] GStreamer API error, falling back to index 0");
                let mut fallback = videoio::VideoCapture::new(0, videoio::CAP_ANY).unwrap();
                let _ = fallback.set(videoio::CAP_PROP_FRAME_WIDTH, 640.0);
                let _ = fallback.set(videoio::CAP_PROP_FRAME_HEIGHT, 480.0);
                fallback
            }
        };

        if !opencv::videoio::VideoCapture::is_opened(&cap).unwrap_or(false) {
            eprintln!("[ERR] Could not open any camera in Rust backend.");
            return;
        }

        let mut frame = core::Mat::default();
        loop {
            match cap.read(&mut frame) {
                Ok(true) => {
                    // Slight resize if not native 640x480 could be done here
                    fm_clone.update(frame.clone());
                    thread::sleep(Duration::from_millis(5)); // yield
                }
                _ => {
                    thread::sleep(Duration::from_millis(50));
                }
            }
        }
    });

    frame_manager
}
