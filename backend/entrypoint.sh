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

# Start gunicorn
# Using 'gthread' worker (standard threads) because 'eventlet' conflicts with PyTorch/OpenCV
exec gunicorn \
    --worker-class gthread \
    --workers 1 \
    --threads 100 \
    --bind 0.0.0.0:5000 \
    --timeout 120 \
    --log-level info \
    app:app
