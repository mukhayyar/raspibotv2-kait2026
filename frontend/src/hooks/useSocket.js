import { useEffect, useState, useRef, useCallback } from 'react';
import { io } from 'socket.io-client';

export function useSocket() {
  const socketRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [authError, setAuthError] = useState('');
  const [status, setStatus] = useState({
    speed: 40, w_angle: 90, h_angle: 90,
    motors: {
      L1: { dir: 0, speed: 0 }, L2: { dir: 0, speed: 0 },
      R1: { dir: 0, speed: 0 }, R2: { dir: 0, speed: 0 },
    },
    led_state: 'off', led_color: 0, buzzer: false,
    direction: 'stopped',
  });
  const [sensors, setSensors] = useState({
    ultrasonic_mm: null,
    line_track: { x1: 0, x2: 0, x3: 0, x4: 0 },
    ir_value: null,
  });
  const [detectionState, setDetectionState] = useState({
    enabled: false,
    confidence: 0.35,
    classes: ['person', 'car', 'dog', 'cat', 'bottle'],
    yolo_available: false,
    detections: [],
  });

  useEffect(() => {
    const socket = io({ transports: ['polling', 'websocket'], upgrade: true });
    socketRef.current = socket;

    socket.on('connect', () => setConnected(true));
    socket.on('disconnect', () => setConnected(false));
    socket.on('status', (data) => setStatus(data));
    socket.on('sensors', (data) => setSensors(data));
    socket.on('detection_state', (data) => setDetectionState(data));
    socket.on('detection_results', (results) => {
      setDetectionState(prev => ({ ...prev, detections: results }));
    });

    // Auth events
    socket.on('auth_result', (data) => {
      if (data.success) {
        setAuthenticated(true);
        setAuthError('');
      } else {
        setAuthError(data.message || 'Incorrect password.');
      }
    });

    return () => { socket.disconnect(); };
  }, []);

  const emit = useCallback((event, data) => {
    socketRef.current?.emit(event, data);
  }, []);

  const authenticate = useCallback((password) => {
    setAuthError('');
    socketRef.current?.emit('authenticate', { password });
  }, []);

  return { connected, authenticated, authError, status, sensors, detectionState, emit, authenticate };
}
