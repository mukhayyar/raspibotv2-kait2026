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

# Force unbuffered stdout/stderr (so logs appear immediately)
ENV PYTHONUNBUFFERED=1

# Create smbus → smbus2 compatibility shim
# Raspbot_Lib uses "import smbus" but we have smbus2 (API-compatible)
RUN python3 -c "import sysconfig; p=sysconfig.get_paths()['purelib']; f=open(p+'/smbus.py','w'); f.write('from smbus2 import SMBus\n'); f.close()" \
    && python3 -c "import smbus; print('smbus shim OK')"

# Copy application code
COPY . .

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Create data directory for SQLite
RUN mkdir -p /app/data

# Expose the backend port
EXPOSE 5000

# Use entrypoint to fix device permissions, then start gunicorn
ENTRYPOINT ["/app/entrypoint.sh"]
