import { useState, useEffect, useCallback, useRef } from 'react';
import { useSocket } from './hooks/useSocket';
import CameraFeed from './components/CameraFeed';
import DPad from './components/DPad';
import ServoSpeed from './components/ServoSpeed';
import LedBuzzer from './components/LedBuzzer';
import SensorPanel from './components/SensorPanel';
import StatusPanel from './components/StatusPanel';
import KeyboardGuide from './components/KeyboardGuide';
import DetectionPanel from './components/DetectionPanel';
import MobileControls from './components/MobileControls';
import './App.css';

/* ─── Key mappings ───────────────────────────────────────────────── */
const KEY_DIR = {
  ArrowUp: 'forward', ArrowDown: 'backward', ArrowLeft: 'left', ArrowRight: 'right',
  w: 'forward', W: 'forward', s: 'backward', S: 'backward',
  a: 'left', A: 'left', d: 'right', D: 'right',
};

const COMBOS = [
  { keys: ['ArrowUp', 'ArrowLeft'], alt: ['w', 'a'], dir: 'forward_left' },
  { keys: ['ArrowUp', 'ArrowRight'], alt: ['w', 'd'], dir: 'forward_right' },
  { keys: ['ArrowDown', 'ArrowLeft'], alt: ['s', 'a'], dir: 'backward_left' },
  { keys: ['ArrowDown', 'ArrowRight'], alt: ['s', 'd'], dir: 'backward_right' },
];

export default function App() {
  const { connected, authenticated, authError, status, sensors, detectionState, emit, authenticate } = useSocket();
  const [activeKeys, setActiveKeys] = useState(new Set());
  const [currentDir, setCurrentDir] = useState(null);
  const [password, setPassword] = useState('');
  const [showAuthDropdown, setShowAuthDropdown] = useState(false);
  const servoRef = useRef(null);

  /* ─── Resolve direction from pressed keys ─── */
  const resolve = useCallback((keys) => {
    for (const c of COMBOS) {
      if (c.keys.every(k => keys.has(k)) ||
          c.alt.every(k => keys.has(k) || keys.has(k.toUpperCase())))
        return c.dir;
    }
    for (const k of keys) {
      if (KEY_DIR[k]) return KEY_DIR[k];
    }
    return null;
  }, []);

  const sendDir = useCallback((dir) => {
    if (!authenticated) return;
    setCurrentDir(prev => {
      if (dir === prev) return prev;
      if (dir) emit('move', { direction: dir });
      else emit('stop');
      return dir;
    });
  }, [emit, authenticated]);

  const handleStop = useCallback(() => {
    setActiveKeys(new Set());
    sendDir(null);
  }, [sendDir]);

  /* ─── Keyboard events ─── */
  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if (!authenticated) return;
      const key = e.key;

      if (KEY_DIR[key] !== undefined) {
        e.preventDefault();
        setActiveKeys(prev => {
          const next = new Set(prev);
          next.add(key);
          sendDir(resolve(next));
          return next;
        });
        return;
      }

      // Servo I/K/J/L
      if (key === 'i' || key === 'I') { e.preventDefault(); servoRef.current?.adjust(2, 2); }
      if (key === 'k' || key === 'K') { e.preventDefault(); servoRef.current?.adjust(2, -2); }
      if (key === 'j' || key === 'J') { e.preventDefault(); servoRef.current?.adjust(1, 2); }
      if (key === 'l' || key === 'L') { e.preventDefault(); servoRef.current?.adjust(1, -2); }

      // Speed presets
      if (key === '1') emit('speed', { speed: 40 });
      if (key === '2') emit('speed', { speed: 70 });
      if (key === '3') emit('speed', { speed: 150 });

      // Buzzer toggle
      if (key === 'b' || key === 'B') {
        emit('buzzer', { state: status.buzzer ? 0 : 1 });
      }

      // Emergency stop
      if (key === ' ' || key === 'Escape') {
        e.preventDefault();
        handleStop();
      }
    };

    const onKeyUp = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      setActiveKeys(prev => {
        const next = new Set(prev);
        next.delete(e.key);
        next.delete(e.key.toLowerCase());
        next.delete(e.key.toUpperCase());
        sendDir(resolve(next));
        return next;
      });
    };

    const onBlur = () => handleStop();

    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    window.addEventListener('blur', onBlur);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      window.removeEventListener('blur', onBlur);
    };
  }, [emit, resolve, sendDir, handleStop, status.buzzer, authenticated]);

  // Guarded emit — child components use this instead of raw emit
  const guardedEmit = useCallback((event, data) => {
    if (!authenticated) return;
    emit(event, data);
  }, [emit, authenticated]);

  return (
    <>
      {/* Header */}
      <header className="header">
        <div className="header-title">
          <span className="logo">🤖</span>
          <h1>PENS-KAIT 2026 — Robot Control</h1>
        </div>
        <div className="keyboard-hint">
          <kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd> Move&ensp;
          <kbd>I</kbd><kbd>J</kbd><kbd>K</kbd><kbd>L</kbd> Servo&ensp;
          <kbd>1</kbd><kbd>2</kbd><kbd>3</kbd> Speed&ensp;
          <kbd>B</kbd> Buzzer&ensp;
          <kbd>Space</kbd> Stop
        </div>
        <div style={{display:'flex', alignItems:'center', gap:8}}>
          {/* Unlock Button */}
          <div style={{position:'relative'}}>
            <button
              onClick={() => { if (!authenticated) setShowAuthDropdown(v => !v); }}
              style={{
                display:'flex', alignItems:'center', gap:4, padding:'5px 12px',
                borderRadius:20, fontSize:'0.75rem', fontWeight:600, cursor: authenticated ? 'default' : 'pointer',
                border: '1px solid',
                background: authenticated ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                borderColor: authenticated ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)',
                color: authenticated ? '#10b981' : '#ef5350',
                transition: 'all 0.2s',
              }}
            >
              {authenticated ? '🔓 Unlocked' : '🔒 Unlock'}
            </button>
            {showAuthDropdown && !authenticated && (
              <div style={{
                position:'absolute', top:'calc(100% + 8px)', right:0, zIndex:200,
                background:'rgba(17,24,39,0.97)', border:'1px solid rgba(99,102,241,0.2)',
                borderRadius:10, padding:10, display:'flex', flexWrap:'wrap', gap:6,
                minWidth:240, boxShadow:'0 12px 40px rgba(0,0,0,0.5)',
                backdropFilter:'blur(12px)',
              }}>
                <input
                  type="password" value={password}
                  onChange={e => setPassword(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); authenticate(password); } }}
                  placeholder="Admin password" autoFocus
                  style={{
                    flex:1, padding:'7px 10px', background:'rgba(255,255,255,0.06)',
                    border:'1px solid rgba(255,255,255,0.12)', borderRadius:6,
                    color:'#fff', fontSize:'0.8rem', outline:'none', minWidth:0,
                  }}
                />
                <button onClick={() => authenticate(password)} style={{
                  padding:'7px 12px', background:'linear-gradient(135deg,#667eea,#764ba2)',
                  border:'none', borderRadius:6, color:'#fff', fontSize:'0.85rem', cursor:'pointer',
                }}>→</button>
                {authError && (
                  <div style={{width:'100%', fontSize:'0.7rem', color:'#ef5350'}}>❌ {authError}</div>
                )}
              </div>
            )}
          </div>
          <div className={`status-badge${connected ? '' : ' disconnected'}`}>
            <span className="status-dot" />
            <span className="status-text">{connected ? 'Connected' : 'Disconnected'}</span>
          </div>
        </div>
      </header>

      {/* Dashboard */}
      <main className="dashboard">
        <CameraFeed />

        <aside className="sidebar">
          <StatusPanel status={status} />
          <SensorPanel sensors={sensors} />
          <DetectionPanel emit={guardedEmit} detectionState={detectionState} />
          <KeyboardGuide activeKeys={activeKeys} />
        </aside>

        <div className="controls-row" style={{
          opacity: authenticated ? 1 : 0.4,
          pointerEvents: authenticated ? 'auto' : 'none',
          transition: 'opacity 0.3s',
        }}>
          <DPad emit={guardedEmit} currentDirection={currentDir} />
          <ServoSpeed ref={servoRef} emit={guardedEmit} status={status} />
          <LedBuzzer emit={guardedEmit} status={status} onStop={handleStop} />
        </div>
      </main>

      {/* Floating mobile D-pads */}
      <MobileControls emit={guardedEmit} authenticated={authenticated} status={status} />
    </>
  );
}
