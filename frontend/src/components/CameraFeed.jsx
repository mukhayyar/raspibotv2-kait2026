import { useEffect, useRef } from 'react';
import './CameraFeed.css';

const STREAM_URL   = '/video_feed';
const STALL_MS     = 8_000;   // reconnect if no new frame for 8 s
const CHECK_MS     = 3_000;   // poll interval

export default function CameraFeed() {
  const imgRef         = useRef(null);
  const lastLoadRef    = useRef(Date.now());
  const reconnectingRef = useRef(false);

  useEffect(() => {
    const img = imgRef.current;
    if (!img) return;

    const onLoad = () => {
      lastLoadRef.current = Date.now();
      reconnectingRef.current = false;
      // Make sure the image is visible again after a successful reconnect
      img.style.display = '';
      const placeholder = img.nextElementSibling;
      if (placeholder) placeholder.style.display = 'none';
    };

    const onError = () => {
      if (!reconnectingRef.current) reconnect();
    };

    const reconnect = () => {
      reconnectingRef.current = true;
      console.warn('[StreamWatchdog] Reconnecting camera feed...');
      img.src = STREAM_URL + '?t=' + Date.now();
    };

    img.addEventListener('load', onLoad);
    img.addEventListener('error', onError);

    const timer = setInterval(() => {
      if (!reconnectingRef.current && Date.now() - lastLoadRef.current > STALL_MS) {
        reconnect();
      }
    }, CHECK_MS);

    return () => {
      img.removeEventListener('load', onLoad);
      img.removeEventListener('error', onError);
      clearInterval(timer);
    };
  }, []);

  return (
    <section className="card camera-section">
      <div className="card-title"><span className="icon">📷</span> Camera Feed</div>
      <img
        ref={imgRef}
        className="camera-feed"
        src={STREAM_URL}
        alt="Camera Feed"
        onError={(e) => {
          e.target.style.display = 'none';
          e.target.nextElementSibling.style.display = 'flex';
        }}
      />
      <div className="camera-feed-placeholder" style={{ display: 'none' }}>
        📷 Camera unavailable
      </div>
    </section>
  );
}
