#!/bin/bash

YOUTUBE_URL="rtmp://a.rtmp.youtube.com/live2"
STREAM_KEY=""
LAB_WEBSITE_URL="http://localhost:5000/research"

# Function to display usage instructions
usage() {
    echo "Usage: $0 -k <STREAM_KEY> -w <WEBSITE_URL> [-y <YOUTUBE_RTMP_URL>]"
    echo "  -k: YouTube Stream Key (Required)"
    echo "  -w: Website URL to capture (Required)"
    echo "  -y: Custom RTMP URL (Optional, defaults to standard YouTube ingest server)"
    exit 1
}

# Verify that required parameters were provided
if [ -z "$STREAM_KEY" ]; then
    echo "Error: Stream key (-k) is required."
    usage
fi

echo "Configuration:"
echo "Website URL: $LAB_WEBSITE_URL"
echo "RTMP Server: $YOUTUBE_URL"
echo "Stream Key: [HIDDEN]"
echo "-----------------------------------"

# 1. Start the virtual display on port :99 with 1080p resolution
echo "Starting Xvfb virtual display..."
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99

# Give Xvfb a second to initialize
sleep 2 

# 2. Launch Chromium in full screen, pointing to your UI
echo "Launching browser..."
chromium-browser --no-sandbox --window-position=0,0 --window-size=1920,1080 --kiosk "$LAB_WEBSITE_URL" &

# 3. Start the FFmpeg streaming loop
while true; do
    echo "Starting stream to YouTube..."
    
    # Capture the virtual screen (:99) and stream for exactly 11h 55m (42900 seconds)
    ffmpeg -f x11grab -video_size 1920x1080 -framerate 30 -i :99 \
    -t 42900 \
    -c:v libx264 -preset veryfast -b:v 4000k -maxrate 4000k -bufsize 8000k \
    -pix_fmt yuv420p -g 60 -c:a aac -b:a 128k -ar 44100 \
    -f flv "$YOUTUBE_URL/$STREAM_KEY"
    
    echo "11 hours and 55 minutes reached. Cutting stream for VOD archive."
    echo "Waiting 15 seconds before resuming..."
    sleep 15
done