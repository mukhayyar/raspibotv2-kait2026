import { useState, useCallback, forwardRef, useImperativeHandle } from 'react';
import './ServoSpeed.css';

const PRESETS = [
  { label: 'Slow', speed: 40 },
  { label: 'Medium', speed: 70 },
  { label: 'Fast', speed: 150 },
  { label: 'Max', speed: 255 },
];

const ServoSpeed = forwardRef(function ServoSpeed({ emit, status }, ref) {
  const [servoH, setServoH] = useState(status.w_angle ?? 90);
  const [servoV, setServoV] = useState(status.h_angle ?? 90);
  const [speed, setSpeed] = useState(status.speed ?? 40);

  const handleServo = useCallback((id, val) => {
    val = Math.max(0, Math.min(180, val));
    if (id === 1) setServoH(val);
    else setServoV(val);
    emit('servo', { id, angle: val });
  }, [emit]);

  const handleSpeed = useCallback((val) => {
    val = Math.max(0, Math.min(255, val));
    setSpeed(val);
    emit('speed', { speed: val });
  }, [emit]);

  // Expose adjust method for keyboard control from parent
  useImperativeHandle(ref, () => ({
    adjust: (id, delta) => {
      if (id === 1) handleServo(1, servoH + delta);
      else handleServo(2, servoV + delta);
    }
  }), [handleServo, servoH, servoV]);

  return (
    <div className="card">
      <div className="card-title"><span className="icon">🎚️</span> Servo & Speed</div>

      <div className="slider-group">
        <div className="slider-label">
          <span>🔄 Horizontal Pan <kbd>J/L</kbd></span>
          <span className="slider-value">{servoH}°</span>
        </div>
        <input type="range" min="0" max="180" value={servoH}
          onChange={(e) => handleServo(1, +e.target.value)} />
      </div>

      <div className="slider-group">
        <div className="slider-label">
          <span>↕️ Vertical Tilt <kbd>I/K</kbd></span>
          <span className="slider-value">{servoV}°</span>
        </div>
        <input type="range" min="0" max="180" value={servoV}
          onChange={(e) => handleServo(2, +e.target.value)} />
      </div>

      <div className="slider-group">
        <div className="slider-label">
          <span>⚡ Speed</span>
          <span className="slider-value">{speed}</span>
        </div>
        <input type="range" min="0" max="255" value={speed}
          onChange={(e) => handleSpeed(+e.target.value)} />
        <div className="speed-presets">
          {PRESETS.map(({ label, speed: s }) => (
            <button key={s}
              className={`preset-btn${speed === s ? ' active' : ''}`}
              onClick={() => handleSpeed(s)}>
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
});

export default ServoSpeed;
