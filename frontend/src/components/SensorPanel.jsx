import './SensorPanel.css';

export default function SensorPanel({ sensors }) {
  const dist = sensors.ultrasonic_mm;
  const distClass = dist != null
    ? (dist < 100 ? ' danger' : dist < 300 ? ' warning' : '')
    : '';

  return (
    <div className="card">
      <div className="card-title"><span className="icon">📡</span> Sensor Data</div>
      <div className="sensor-grid">
        <div className="sensor-card">
          <div className="sensor-icon">📏</div>
          <div className="sensor-label">Ultrasonic</div>
          <div className={`sensor-value${distClass}`}>
            {dist != null ? dist : '---'}
          </div>
          <div className="sensor-unit">mm</div>
        </div>
        <div className="sensor-card">
          <div className="sensor-icon">📡</div>
          <div className="sensor-label">IR Remote</div>
          <div className="sensor-value">
            {sensors.ir_value != null ? sensors.ir_value : '---'}
          </div>
          <div className="sensor-unit">value</div>
        </div>
      </div>
      <div className="line-track-section">
        <div className="sensor-label" style={{ textAlign: 'center', marginBottom: 6 }}>
          Line Tracking
        </div>
        <div className="line-track-viz">
          {['x1', 'x2', 'x3', 'x4'].map((k, i) => (
            <div key={k}
              className={`track-sensor${sensors.line_track?.[k] === 1 ? ' on' : ''}`}>
              {i + 1}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
