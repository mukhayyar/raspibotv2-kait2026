/* ═══════════════════════════════════════════════════════════════════
   PENS-KAIT 2026 — Robot Control Dashboard — Socket.IO Client
   Real-time keyboard + click controls for the Yahboom Raspbot
   ═══════════════════════════════════════════════════════════════════ */

// ─── Socket.IO Connection ────────────────────────────────────────────
const socket = io({ transports: ['polling', 'websocket'], upgrade: true });

// ─── Authentication ──────────────────────────────────────────────────
let isAuthenticated = false;

function toggleAuthForm() {
    if (isAuthenticated) return;
    const dd = document.getElementById('auth-dropdown');
    dd.classList.toggle('hidden');
    if (!dd.classList.contains('hidden')) {
        setTimeout(() => document.getElementById('auth-password')?.focus(), 50);
    }
}

function submitAuth() {
    const input = document.getElementById('auth-password');
    const fb = document.getElementById('auth-feedback');
    const pwd = input.value.trim();
    if (!pwd) { fb.textContent = 'Please enter a password.'; fb.className = 'auth-feedback error'; return; }
    fb.textContent = '⏳ Verifying...'; fb.className = 'auth-feedback';
    socket.emit('authenticate', { password: pwd });
}

socket.on('auth_result', (data) => {
    const fb = document.getElementById('auth-feedback');
    const btn = document.getElementById('auth-toggle-btn');
    const btnText = document.getElementById('auth-btn-text');
    const dd = document.getElementById('auth-dropdown');
    if (data.success) {
        isAuthenticated = true;
        fb.textContent = '✅ Unlocked!'; fb.className = 'auth-feedback success';
        setTimeout(() => {
            dd.classList.add('hidden');
            btn.className = 'auth-btn unlocked';
            btn.innerHTML = '🔓 <span id="auth-btn-text">Unlocked</span>';
        }, 400);
    } else {
        fb.textContent = '❌ ' + (data.message || 'Incorrect password.');
        fb.className = 'auth-feedback error';
        document.getElementById('auth-password').value = '';
        document.getElementById('auth-password').focus();
    }
});

socket.on('auth_state', (data) => {
    if (data.authenticated) {
        isAuthenticated = true;
        const btn = document.getElementById('auth-toggle-btn');
        btn.className = 'auth-btn unlocked';
        btn.innerHTML = '🔓 <span id="auth-btn-text">Unlocked</span>';
    }
});

// ─── State ───────────────────────────────────────────────────────────
let currentDirection = null;
let activeKeys = new Set();

// ─── Keyboard → Direction Map ────────────────────────────────────────
const KEY_DIR_MAP = {
    'ArrowUp': 'forward', 'ArrowDown': 'backward',
    'ArrowLeft': 'left',  'ArrowRight': 'right',
    'w': 'forward', 'W': 'forward',
    's': 'backward', 'S': 'backward',
    'a': 'left', 'A': 'left',
    'd': 'right', 'D': 'right',
};

const COMBO_MAP = [
    { keys: ['ArrowUp','ArrowLeft'],    alt: ['w','a'], dir: 'forward_left' },
    { keys: ['ArrowUp','ArrowRight'],   alt: ['w','d'], dir: 'forward_right' },
    { keys: ['ArrowDown','ArrowLeft'],  alt: ['s','a'], dir: 'backward_left' },
    { keys: ['ArrowDown','ArrowRight'], alt: ['s','d'], dir: 'backward_right' },
];

const KEY_VISUAL = {
    'w': 'key-w', 'ArrowUp': 'key-w',
    'a': 'key-a', 'ArrowLeft': 'key-a',
    's': 'key-s', 'ArrowDown': 'key-s',
    'd': 'key-d', 'ArrowRight': 'key-d',
};

// ─── Socket.IO Events ───────────────────────────────────────────────
socket.on('connect', () => {
    console.log('[WS] Connected');
    updateStatusBadge(true);
});

socket.on('disconnect', () => {
    console.log('[WS] Disconnected');
    updateStatusBadge(false);
});

socket.on('status', (data) => {
    updateStatusUI(data);
});

socket.on('sensors', (data) => {
    updateSensorUI(data);
});

// ─── Movement ────────────────────────────────────────────────────────
function resolveDirection() {
    for (const combo of COMBO_MAP) {
        if (combo.keys.every(k => activeKeys.has(k)) ||
            combo.alt.every(k => activeKeys.has(k) || activeKeys.has(k.toUpperCase())))
            return combo.dir;
    }
    for (const key of activeKeys) {
        if (KEY_DIR_MAP[key]) return KEY_DIR_MAP[key];
    }
    return null;
}

function sendDirection(dir) {
    if (!isAuthenticated) return;
    if (dir === currentDirection) return;
    currentDirection = dir;
    if (dir) {
        socket.emit('move', { direction: dir });
    } else {
        socket.emit('stop');
    }
    updateDpadHighlight(dir);
}

function updateDpadHighlight(dir) {
    document.querySelectorAll('.dpad-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.dir === dir);
    });
}

// ─── Keyboard Events ─────────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (!isAuthenticated) return;
    const key = e.key;

    if (KEY_DIR_MAP[key] !== undefined) {
        e.preventDefault();
        activeKeys.add(key);
        highlightKeyGuide();
        sendDirection(resolveDirection());
        return;
    }

    // Servo: I/K vertical, J/L horizontal
    if (key === 'i' || key === 'I') { e.preventDefault(); adjustServo(2, 2); }
    if (key === 'k' || key === 'K') { e.preventDefault(); adjustServo(2, -2); }
    if (key === 'j' || key === 'J') { e.preventDefault(); adjustServo(1, 2); }
    if (key === 'l' || key === 'L') { e.preventDefault(); adjustServo(1, -2); }

    // Speed presets
    if (key === '1') setSpeed(40);
    if (key === '2') setSpeed(70);
    if (key === '3') setSpeed(150);

    // Buzzer toggle
    if (key === 'b' || key === 'B') {
        const t = document.getElementById('buzzer-toggle');
        t.checked = !t.checked;
        toggleBuzzer(t.checked);
    }

    // Emergency stop
    if (key === ' ' || key === 'Escape') {
        e.preventDefault();
        activeKeys.clear();
        highlightKeyGuide();
        sendDirection(null);
    }
});

document.addEventListener('keyup', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    activeKeys.delete(e.key);
    activeKeys.delete(e.key.toLowerCase());
    activeKeys.delete(e.key.toUpperCase());
    highlightKeyGuide();
    sendDirection(resolveDirection());
});

window.addEventListener('blur', () => {
    activeKeys.clear();
    highlightKeyGuide();
    sendDirection(null);
});

function highlightKeyGuide() {
    document.querySelectorAll('.key-cell').forEach(el => el.classList.remove('active'));
    for (const key of activeKeys) {
        const id = KEY_VISUAL[key] || KEY_VISUAL[key.toLowerCase()];
        if (id) document.getElementById(id)?.classList.add('active');
    }
}

// ─── D-Pad Click/Touch ───────────────────────────────────────────────
function setupDpad() {
    document.querySelectorAll('.dpad-btn').forEach(btn => {
        const dir = btn.dataset.dir;
        const start = (e) => { e.preventDefault(); if (!isAuthenticated) return; sendDirection(dir === 'stop' ? null : dir); };
        const end = (e) => { e.preventDefault(); if (!isAuthenticated) return; if (dir !== 'stop') sendDirection(null); };
        btn.addEventListener('mousedown', start);
        btn.addEventListener('touchstart', start, { passive: false });
        btn.addEventListener('mouseup', end);
        btn.addEventListener('mouseleave', end);
        btn.addEventListener('touchend', end);
        btn.addEventListener('touchcancel', end);
    });
}

// ─── Servo Control ───────────────────────────────────────────────────
function adjustServo(id, delta) {
    if (!isAuthenticated) return;
    const slider = document.getElementById(id === 1 ? 'servo-h' : 'servo-v');
    let val = Math.max(0, Math.min(180, parseInt(slider.value) + delta));
    slider.value = val;
    document.getElementById(id === 1 ? 'servo-h-val' : 'servo-v-val').textContent = val + '°';
    socket.emit('servo', { id, angle: val });
}

function onServoChange(id, slider) {
    if (!isAuthenticated) return;
    const val = parseInt(slider.value);
    document.getElementById(id === 1 ? 'servo-h-val' : 'servo-v-val').textContent = val + '°';
    socket.emit('servo', { id, angle: val });
}

// ─── Speed Control ───────────────────────────────────────────────────
function setSpeed(val) {
    if (!isAuthenticated) return;
    val = Math.max(0, Math.min(255, val));
    document.getElementById('speed-slider').value = val;
    document.getElementById('speed-val').textContent = val;
    updateSpeedPresets(val);
    socket.emit('speed', { speed: val });
}

function onSpeedChange(slider) {
    if (!isAuthenticated) return;
    const val = parseInt(slider.value);
    document.getElementById('speed-val').textContent = val;
    updateSpeedPresets(val);
    socket.emit('speed', { speed: val });
}

function updateSpeedPresets(val) {
    document.querySelectorAll('.preset-btn').forEach(btn => {
        btn.classList.toggle('active', parseInt(btn.dataset.speed) === val);
    });
}

// ─── LED Control ─────────────────────────────────────────────────────
function setLedColor(color) {
    if (!isAuthenticated) return;
    document.querySelectorAll('.led-color-btn').forEach(btn => {
        btn.classList.toggle('active', parseInt(btn.dataset.color) === color);
    });
    socket.emit('led', { action: 'on', color });
}

function setLedOff() {
    if (!isAuthenticated) return;
    document.querySelectorAll('.led-color-btn').forEach(btn => btn.classList.remove('active'));
    socket.emit('led', { action: 'off' });
}

// ─── Buzzer ──────────────────────────────────────────────────────────
function toggleBuzzer(on) {
    if (!isAuthenticated) return;
    socket.emit('buzzer', { state: on ? 1 : 0 });
}

// ─── UI Update Handlers ─────────────────────────────────────────────
function updateSensorUI(data) {
    const distEl = document.getElementById('sensor-distance');
    if (data.ultrasonic_mm != null) {
        distEl.textContent = data.ultrasonic_mm;
        distEl.className = 'sensor-value' +
            (data.ultrasonic_mm < 100 ? ' danger' : data.ultrasonic_mm < 300 ? ' warning' : '');
    } else {
        distEl.textContent = '---';
        distEl.className = 'sensor-value';
    }

    if (data.line_track) {
        ['x1','x2','x3','x4'].forEach(k => {
            document.getElementById('track-' + k)?.classList.toggle('on', data.line_track[k] === 1);
        });
    }

    const irEl = document.getElementById('sensor-ir');
    irEl.textContent = data.ir_value != null ? data.ir_value : '---';
}

function updateStatusUI(data) {
    document.getElementById('status-speed').textContent = data.speed;
    document.getElementById('status-servo-h').textContent = data.w_angle + '°';
    document.getElementById('status-servo-v').textContent = data.h_angle + '°';

    const dirEl = document.getElementById('status-direction');
    dirEl.textContent = data.direction.replace('_', ' ');
    dirEl.className = 'dir-value' + (data.direction === 'stopped' ? ' stopped' : '');

    document.getElementById('status-led').textContent = data.led_state;
    document.getElementById('status-buzzer').textContent = data.buzzer ? 'ON' : 'OFF';

    for (const [name, motor] of Object.entries(data.motors)) {
        const el = document.getElementById('motor-' + name);
        if (!el) continue;
        el.querySelector('.motor-speed-val').textContent = motor.speed;
        el.querySelector('.motor-dir').textContent = motor.speed > 0 ? (motor.dir === 0 ? 'FWD' : 'REV') : '---';
        el.classList.toggle('running', motor.speed > 0);
    }
}

function updateStatusBadge(connected) {
    const badge = document.getElementById('status-badge');
    badge.className = connected ? 'status-badge' : 'status-badge disconnected';
    badge.querySelector('.status-text').textContent = connected ? 'Connected' : 'Disconnected';
}

// ─── YOLO Detection ──────────────────────────────────────────────────
socket.on('detection_state', (data) => {
    document.getElementById('detection-toggle').checked = data.enabled;
    document.getElementById('det-conf-slider').value = Math.round(data.confidence * 100);
    document.getElementById('det-conf-val').textContent = data.confidence.toFixed(2);
    document.getElementById('det-classes').value = (data.classes || []).join(', ');
    const statusEl = document.getElementById('det-status');
    statusEl.textContent = data.yolo_available ? '✅ YOLO model loaded' : '⚠️ YOLO unavailable';
});

socket.on('detection_results', (results) => {
    // Only show results if detection is explicitly enabled in this UI
    const toggle = document.getElementById('detection-toggle');
    if (!toggle || !toggle.checked) return;

    const el = document.getElementById('det-results');
    if (!results || results.length === 0) {
        el.textContent = 'No detections';
        return;
    }
    // Count by class
    const counts = {};
    results.forEach(d => {
        counts[d.class] = (counts[d.class] || 0) + 1;
    });
    el.innerHTML = Object.entries(counts)
        .map(([cls, count]) => `<span style="margin-right:8px;"><strong>${cls}</strong>: ${count}</span>`)
        .join('');
});

function toggleDetection(on) {
    socket.emit('detection_toggle', { enabled: on });
}

function onConfidenceChange(slider) {
    const val = parseInt(slider.value) / 100;
    document.getElementById('det-conf-val').textContent = val.toFixed(2);
    socket.emit('detection_config', { confidence: val });
}

function applyClasses() {
    const input = document.getElementById('det-classes');
    const classes = input.value.split(',').map(c => c.trim()).filter(c => c);
    if (classes.length === 0) return;
    const fb = document.getElementById('det-class-feedback');
    if (fb) { fb.textContent = '⏳ Applying...'; fb.style.color = 'var(--text-muted)'; }
    socket.emit('detection_config', { classes });
}

// Kept for backward compat — redirects to applyClasses
function onClassesChange(input) { applyClasses(); }

// ─── Class Update Feedback ───────────────────────────────────────────
socket.on('detection_class_update', (data) => {
    const fb = document.getElementById('det-class-feedback');
    if (!fb) return;
    if (data.success) {
        fb.textContent = '✅ Classes updated: ' + (data.classes || []).join(', ');
        fb.style.color = '#4caf50';
    } else {
        fb.textContent = '❌ ' + (data.error || 'Unknown error');
        fb.style.color = '#ef5350';
    }
    setTimeout(() => { fb.textContent = ''; }, 6000);
});

// ─── Mobile Floating Controls ────────────────────────────────────────
function setupMobileControls() {
    // Movement buttons
    document.querySelectorAll('[data-fly-move]').forEach(btn => {
        const dir = btn.dataset.flyMove;
        const start = (e) => {
            e.preventDefault();
            if (!isAuthenticated) return;
            btn.classList.add('pressed');
            if (navigator.vibrate) navigator.vibrate(20);
            if (dir === 'stop') {
                currentDirection = null;
                socket.emit('stop');
            } else {
                currentDirection = dir;
                socket.emit('move', { direction: dir });
            }
        };
        const end = (e) => {
            e.preventDefault();
            btn.classList.remove('pressed');
            if (!isAuthenticated) return;
            if (dir !== 'stop') {
                currentDirection = null;
                socket.emit('stop');
            }
        };
        btn.addEventListener('touchstart', start, { passive: false });
        btn.addEventListener('mousedown', start);
        btn.addEventListener('touchend', end);
        btn.addEventListener('touchcancel', end);
        btn.addEventListener('mouseup', end);
        btn.addEventListener('mouseleave', () => btn.classList.remove('pressed'));
    });

    // Servo buttons
    const SERVO_MAP = { up: [2, 5], down: [2, -5], left: [1, 5], right: [1, -5] };
    let servoInterval = null;

    document.querySelectorAll('[data-fly-servo]').forEach(btn => {
        const action = btn.dataset.flyServo;
        const start = (e) => {
            e.preventDefault();
            if (!isAuthenticated) return;
            btn.classList.add('pressed');
            if (navigator.vibrate) navigator.vibrate(20);
            if (action === 'center') {
                // Reset both servos to center
                socket.emit('servo', { id: 1, angle: 90 });
                socket.emit('servo', { id: 2, angle: 90 });
                const sh = document.getElementById('servo-h');
                const sv = document.getElementById('servo-v');
                if (sh) { sh.value = 90; document.getElementById('servo-h-val').textContent = '90°'; }
                if (sv) { sv.value = 90; document.getElementById('servo-v-val').textContent = '90°'; }
                return;
            }
            const [id, delta] = SERVO_MAP[action];
            adjustServo(id, delta);
            servoInterval = setInterval(() => adjustServo(id, delta), 120);
        };
        const end = (e) => {
            e.preventDefault();
            btn.classList.remove('pressed');
            if (servoInterval) { clearInterval(servoInterval); servoInterval = null; }
        };
        btn.addEventListener('touchstart', start, { passive: false });
        btn.addEventListener('mousedown', start);
        btn.addEventListener('touchend', end);
        btn.addEventListener('touchcancel', end);
        btn.addEventListener('mouseup', end);
        btn.addEventListener('mouseleave', () => {
            btn.classList.remove('pressed');
            if (servoInterval) { clearInterval(servoInterval); servoInterval = null; }
        });
    });
}

// ─── Init ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    setupDpad();
    setupMobileControls();
});
