mod camera;
mod yolo;

use axum::{routing::get, Router};
use std::net::SocketAddr;
use tower_http::cors::CorsLayer;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("[INFO] Starting PENS-KAIT 2026 Rust Backend...");

    // 1. Initialize YOLO
    // let yolo = yolo::YoloModel::new("../backend/models/yolov8s-worldv2.onnx")?;

    // 2. Start Camera
    let _frame_manager = camera::start_camera_thread();

    // 3. Setup router (to be integrated with socketioxide)
    let app = Router::new()
        .route("/", get(|| async { "Rust Backend Running" }))
        .layer(CorsLayer::permissive());

    let addr = SocketAddr::from(([0, 0, 0, 0], 8080));
    println!("[INFO] Listening on http://{}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}
