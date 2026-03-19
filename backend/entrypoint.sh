#!/bin/bash

# Fix I2C device permissions (needs privileged mode via sudo docker compose)
if [ -e /dev/i2c-1 ]; then
    chmod 666 /dev/i2c-1 2>/dev/null && echo "[entrypoint] /dev/i2c-1 permissions set to 666" \
        || echo "[entrypoint] WARNING: Could not chmod /dev/i2c-1 — run with: sudo docker compose up"
fi

# Fix video device permissions
if [ -e /dev/video0 ]; then
    chmod 666 /dev/video0 2>/dev/null && echo "[entrypoint] /dev/video0 permissions set to 666" \
        || echo "[entrypoint] WARNING: Could not chmod /dev/video0"
fi

# Start the application using the standard Flask-SocketIO server.
# We avoid Gunicorn here because its thread workers don't support WebSockets,
# which causes the React/web client to endlessly hang during the upgrade process.
echo "[entrypoint] Starting Python server on port 5000..."
exec python app.py
