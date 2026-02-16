FROM python:3.11-slim

# System deps for OpenCV + camera + I2C support
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    i2c-tools \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for SQLite
RUN mkdir -p /app/data

# Raspbot_Lib is mounted at runtime via docker-compose volume
# The sys.path manipulation in app.py handles the import

# Expose the backend port
EXPOSE 5000

# Use gunicorn with eventlet for production Socket.IO
CMD ["gunicorn", \
     "--worker-class", "eventlet", \
     "--workers", "1", \
     "--bind", "0.0.0.0:5000", \
     "--timeout", "120", \
     "--log-level", "info", \
     "app:app"]
