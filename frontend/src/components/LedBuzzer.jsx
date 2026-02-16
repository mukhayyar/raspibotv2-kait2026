import { useState, useCallback } from 'react';
import './LedBuzzer.css';

const COLORS = [
  { id: 0, label: 'Red' },
  { id: 1, label: 'Green' },
  { id: 2, label: 'Blue' },
  { id: 3, label: 'Yellow' },
  { id: 4, label: 'Purple' },
  { id: 5, label: 'Cyan' },
  { id: 6, label: 'White' },
];

export default function LedBuzzer({ emit, status, onStop }) {
  const [activeColor, setActiveColor] = useState(null);

  const setLed = useCallback((color) => {
    setActiveColor(color);
    emit('led', { action: 'on', color });
  }, [emit]);

  const ledOff = useCallback(() => {
    setActiveColor(null);
    emit('led', { action: 'off' });
  }, [emit]);

  const toggleBuzzer = useCallback((on) => {
    emit('buzzer', { state: on ? 1 : 0 });
  }, [emit]);

  return (
    <div className="card">
      <div className="card-title"><span className="icon">💡</span> LED & Buzzer</div>

      <div className="led-section">
        <div className="slider-label" style={{ marginBottom: 8 }}>
          <span>LED Color</span>
        </div>
        <div className="led-colors">
          {COLORS.map(({ id, label }) => (
            <button key={id}
              className={`led-color-btn color-${id}${activeColor === id ? ' active' : ''}`}
              title={label}
              onClick={() => setLed(id)}
            />
          ))}
        </div>
        <div className="led-toggle-row">
          <button className="action-btn primary" onClick={() => setLed(activeColor ?? 0)}>💡 LED ON</button>
          <button className="action-btn danger" onClick={ledOff}>LED OFF</button>
        </div>
      </div>

      <div className="toggle-row">
        <label>🔊 Buzzer <kbd>B</kbd></label>
        <label className="toggle">
          <input type="checkbox"
            checked={status.buzzer}
            onChange={(e) => toggleBuzzer(e.target.checked)}
          />
          <span className="toggle-slider" />
        </label>
      </div>

      <button className="action-btn danger stop-btn" onClick={onStop}>
        🛑 EMERGENCY STOP (Space)
      </button>
    </div>
  );
}
