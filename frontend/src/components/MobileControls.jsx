import { useRef, useCallback } from 'react';
import './MobileControls.css';

const MOVE_DIRS = [
  { dir: 'forward_left', label: '↖' },
  { dir: 'forward', label: '⬆' },
  { dir: 'forward_right', label: '↗' },
  { dir: 'left', label: '⬅' },
  { dir: 'stop', label: '⏹', cls: 'fly-stop' },
  { dir: 'right', label: '➡' },
  { dir: 'backward_left', label: '↙' },
  { dir: 'backward', label: '⬇' },
  { dir: 'backward_right', label: '↘' },
];

const SERVO_DIRS = [
  { action: null },
  { action: 'up', label: '⬆', id: 2, delta: 5 },
  { action: null },
  { action: 'left', label: '⬅', id: 1, delta: 5 },
  { action: 'center', label: '⊙', cls: 'fly-center' },
  { action: 'right', label: '➡', id: 1, delta: -5 },
  { action: null },
  { action: 'down', label: '⬇', id: 2, delta: -5 },
  { action: null },
];

export default function MobileControls({ emit, authenticated, status }) {
  const servoIntervalRef = useRef(null);
  // Track local servo angles (init from status or default 90)
  const servoAngles = useRef({ 1: 90, 2: 90 });

  // Sync from status when available
  if (status?.servo_h != null) servoAngles.current[1] = status.servo_h;
  if (status?.servo_v != null) servoAngles.current[2] = status.servo_v;

  const vibrate = () => { if (navigator.vibrate) navigator.vibrate(20); };

  /* ─── Movement handlers ─── */
  const moveStart = useCallback((dir) => (e) => {
    e.preventDefault();
    if (!authenticated) return;
    vibrate();
    if (dir === 'stop') emit('stop');
    else emit('move', { direction: dir });
  }, [emit, authenticated]);

  const moveEnd = useCallback((dir) => (e) => {
    e.preventDefault();
    if (!authenticated) return;
    if (dir !== 'stop') emit('stop');
  }, [emit, authenticated]);

  /* ─── Servo handlers ─── */
  const nudgeServo = useCallback((id, delta) => {
    const angles = servoAngles.current;
    angles[id] = Math.max(0, Math.min(180, angles[id] + delta));
    emit('servo', { id, angle: angles[id] });
  }, [emit]);

  const servoStart = useCallback((action, id, delta) => (e) => {
    e.preventDefault();
    if (!authenticated) return;
    vibrate();
    if (action === 'center') {
      servoAngles.current[1] = 90;
      servoAngles.current[2] = 90;
      emit('servo', { id: 1, angle: 90 });
      emit('servo', { id: 2, angle: 90 });
      return;
    }
    nudgeServo(id, delta);
    servoIntervalRef.current = setInterval(() => nudgeServo(id, delta), 120);
  }, [emit, authenticated, nudgeServo]);

  const servoEnd = useCallback(() => (e) => {
    e.preventDefault();
    if (servoIntervalRef.current) {
      clearInterval(servoIntervalRef.current);
      servoIntervalRef.current = null;
    }
  }, []);

  return (
    <div className="mobile-controls">
      {/* Movement D-Pad (Left) */}
      <div className="fly-pad fly-pad-left">
        <div className="fly-pad-label">🕹 Move</div>
        <div className="fly-dpad">
          {MOVE_DIRS.map(({ dir, label, cls }) => (
            <button
              key={dir}
              className={`fly-btn ${cls || ''}`}
              onTouchStart={moveStart(dir)}
              onTouchEnd={moveEnd(dir)}
              onTouchCancel={moveEnd(dir)}
              onMouseDown={moveStart(dir)}
              onMouseUp={moveEnd(dir)}
              onMouseLeave={moveEnd(dir)}
            >{label}</button>
          ))}
        </div>
      </div>

      {/* Servo D-Pad (Right) */}
      <div className="fly-pad fly-pad-right">
        <div className="fly-pad-label">🎯 Servo</div>
        <div className="fly-dpad">
          {SERVO_DIRS.map((item, i) =>
            item.action === null ? (
              <div key={i} className="fly-spacer" />
            ) : (
              <button
                key={item.action}
                className={`fly-btn ${item.cls || ''}`}
                onTouchStart={servoStart(item.action, item.id, item.delta)}
                onTouchEnd={servoEnd()}
                onTouchCancel={servoEnd()}
                onMouseDown={servoStart(item.action, item.id, item.delta)}
                onMouseUp={servoEnd()}
                onMouseLeave={servoEnd()}
              >{item.label}</button>
            )
          )}
        </div>
      </div>
    </div>
  );
}
