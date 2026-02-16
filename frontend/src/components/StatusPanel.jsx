import './StatusPanel.css';

export default function StatusPanel({ status }) {
  return (
    <div className="card">
      <div className="card-title"><span className="icon">📊</span> Robot Status</div>
      <div className="direction-display">
        <div className="dir-label">Direction</div>
        <div className={`dir-value${status.direction === 'stopped' ? ' stopped' : ''}`}>
          {status.direction.replace('_', ' ').toUpperCase()}
        </div>
      </div>
      <table className="status-table">
        <tbody>
          <tr><td>Speed</td><td>{status.speed}</td></tr>
          <tr><td>Servo H (Pan)</td><td>{status.w_angle}°</td></tr>
          <tr><td>Servo V (Tilt)</td><td>{status.h_angle}°</td></tr>
          <tr><td>LED</td><td>{status.led_state}</td></tr>
          <tr><td>Buzzer</td><td>{status.buzzer ? 'ON' : 'OFF'}</td></tr>
        </tbody>
      </table>
      <div className="motors-grid">
        {['L1', 'R1', 'L2', 'R2'].map(name => {
          const motor = status.motors?.[name] || { speed: 0, dir: 0 };
          return (
            <div key={name} className={`motor-indicator${motor.speed > 0 ? ' running' : ''}`}>
              <div className="motor-name">{name}</div>
              <div className="motor-speed-val">{motor.speed}</div>
              <div className="motor-dir">
                {motor.speed > 0 ? (motor.dir === 0 ? 'FWD' : 'REV') : '---'}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
