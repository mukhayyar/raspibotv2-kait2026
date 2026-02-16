import './CameraFeed.css';

export default function CameraFeed() {
  return (
    <section className="card camera-section">
      <div className="card-title"><span className="icon">📷</span> Camera Feed</div>
      <img
        className="camera-feed"
        src="/video_feed"
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
