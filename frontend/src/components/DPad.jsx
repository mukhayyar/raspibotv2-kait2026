import { useRef, useCallback } from 'react';
import './DPad.css';

const DIRS = [
  { dir: 'forward_left', label: '↖' },
  { dir: 'forward', label: '⬆' },
  { dir: 'forward_right', label: '↗' },
  { dir: 'left', label: '⬅' },
  { dir: 'stop', label: '⏹' },
  { dir: 'right', label: '➡' },
  { dir: 'backward_left', label: '↙' },
  { dir: 'backward', label: '⬇' },
  { dir: 'backward_right', label: '↘' },
];

export default function DPad({ emit, currentDirection }) {
  const activeRef = useRef(null);

  const start = useCallback((dir) => (e) => {
    e.preventDefault();
    if (dir === 'stop') {
      emit('stop');
      activeRef.current = null;
    } else {
      emit('move', { direction: dir });
      activeRef.current = dir;
    }
  }, [emit]);

  const end = useCallback((dir) => (e) => {
    e.preventDefault();
    if (dir !== 'stop') {
      emit('stop');
      activeRef.current = null;
    }
  }, [emit]);

  return (
    <div className="card">
      <div className="card-title"><span className="icon">🕹️</span> Movement</div>
      <div className="dpad-container">
        <div className="dpad">
          {DIRS.map(({ dir, label }) => (
            <button
              key={dir}
              className={`dpad-btn${currentDirection === dir ? ' active' : ''}`}
              onMouseDown={start(dir)}
              onMouseUp={end(dir)}
              onMouseLeave={end(dir)}
              onTouchStart={start(dir)}
              onTouchEnd={end(dir)}
              onTouchCancel={end(dir)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
