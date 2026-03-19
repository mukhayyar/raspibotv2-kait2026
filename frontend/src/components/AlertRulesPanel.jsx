import { useState, useCallback } from 'react';
import './AlertRulesPanel.css';

const ACTION_TYPES = [
  { value: 'led_color', label: 'LED Color' },
  { value: 'led_rgb', label: 'LED RGB' },
  { value: 'buzzer_on', label: 'Buzzer On' },
  { value: 'buzzer_pattern', label: 'Buzzer Pattern' },
];

const LED_COLORS = [
  { id: 0, label: 'Red', hex: '#e74c3c' },
  { id: 1, label: 'Green', hex: '#2ecc71' },
  { id: 2, label: 'Blue', hex: '#3498db' },
  { id: 3, label: 'Yellow', hex: '#f1c40f' },
  { id: 4, label: 'Purple', hex: '#9b59b6' },
  { id: 5, label: 'Cyan', hex: '#1abc9c' },
  { id: 6, label: 'White', hex: '#ecf0f1' },
];

const ACTION_LABELS = {
  led_color: (p) => {
    const c = LED_COLORS.find(c => c.id === p?.color);
    return c ? `LED ${c.label}` : 'LED';
  },
  led_rgb: (p) => `LED (${p?.r ?? 0},${p?.g ?? 0},${p?.b ?? 0})`,
  buzzer_on: () => 'Buzzer',
  buzzer_pattern: (p) => `Beep ${p?.repeats ?? 3}x`,
};

export default function AlertRulesPanel({ emit, detectionState, alertRules, triggeredAlerts }) {
  const classes = detectionState?.classes || [];
  const [showForm, setShowForm] = useState(false);
  const [formClass, setFormClass] = useState('');
  const [formThreshold, setFormThreshold] = useState(1);
  const [formAction, setFormAction] = useState('led_color');
  const [formColor, setFormColor] = useState(0);
  const [formR, setFormR] = useState(255);
  const [formG, setFormG] = useState(0);
  const [formB, setFormB] = useState(0);
  const [formOnMs, setFormOnMs] = useState(200);
  const [formOffMs, setFormOffMs] = useState(200);
  const [formRepeats, setFormRepeats] = useState(3);

  const syncRules = useCallback((rules) => {
    emit('alert_rules_sync', { rules });
  }, [emit]);

  const addRule = useCallback(() => {
    const className = formClass || classes[0] || 'person';
    let actionParams = {};
    if (formAction === 'led_color') actionParams = { color: formColor };
    else if (formAction === 'led_rgb') actionParams = { r: formR, g: formG, b: formB };
    else if (formAction === 'buzzer_pattern') actionParams = { on_ms: formOnMs, off_ms: formOffMs, repeats: formRepeats };

    const newRule = {
      id: crypto.randomUUID(),
      class_name: className,
      count_threshold: formThreshold,
      action_type: formAction,
      action_params: actionParams,
      enabled: true,
    };
    syncRules([...alertRules, newRule]);
    setShowForm(false);
  }, [formClass, formThreshold, formAction, formColor, formR, formG, formB, formOnMs, formOffMs, formRepeats, alertRules, classes, syncRules]);

  const removeRule = useCallback((id) => {
    syncRules(alertRules.filter(r => r.id !== id));
  }, [alertRules, syncRules]);

  const toggleRule = useCallback((id) => {
    syncRules(alertRules.map(r => r.id === id ? { ...r, enabled: !r.enabled } : r));
  }, [alertRules, syncRules]);

  return (
    <div className="card alert-rules-panel">
      <div className="card-title"><span className="icon">&#x26A1;</span> Detection Alerts</div>

      {/* Existing rules */}
      {alertRules.length === 0 && (
        <div className="alert-empty">No alert rules configured</div>
      )}
      <div className="alert-rules-list">
        {alertRules.map(rule => {
          const fired = !!triggeredAlerts[rule.id];
          const actionLabel = ACTION_LABELS[rule.action_type]?.(rule.action_params) || rule.action_type;
          return (
            <div key={rule.id} className={`alert-rule-row${fired ? ' fired' : ''}${!rule.enabled ? ' disabled' : ''}`}>
              <div className="alert-rule-indicator">
                <span className={`alert-dot${fired ? ' active' : ''}`} />
              </div>
              <div className="alert-rule-info">
                <span className="alert-rule-class">{rule.class_name}</span>
                <span className="alert-rule-op">&ge;{rule.count_threshold}</span>
                <span className="alert-rule-arrow">&rarr;</span>
                <span className="alert-rule-action">{actionLabel}</span>
              </div>
              <div className="alert-rule-controls">
                <label className="toggle toggle-sm">
                  <input type="checkbox" checked={rule.enabled} onChange={() => toggleRule(rule.id)} />
                  <span className="toggle-slider" />
                </label>
                <button className="alert-delete-btn" onClick={() => removeRule(rule.id)} title="Remove rule">&times;</button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Add rule button / form */}
      {!showForm ? (
        <button className="alert-add-btn" onClick={() => { setFormClass(classes[0] || ''); setShowForm(true); }}>
          + Add Alert Rule
        </button>
      ) : (
        <div className="alert-form">
          <div className="alert-form-title">New Alert Rule</div>

          {/* Class selector */}
          <div className="alert-form-row">
            <label>When</label>
            <select value={formClass} onChange={e => setFormClass(e.target.value)}>
              {classes.map(c => <option key={c} value={c}>{c}</option>)}
              <option value="_custom">Custom...</option>
            </select>
          </div>
          {formClass === '_custom' && (
            <div className="alert-form-row">
              <label>Class</label>
              <input type="text" placeholder="class name" onChange={e => setFormClass(e.target.value)} />
            </div>
          )}

          {/* Threshold */}
          <div className="alert-form-row">
            <label>Count &ge;</label>
            <input type="number" min="1" max="50" value={formThreshold}
              onChange={e => setFormThreshold(Math.max(1, parseInt(e.target.value) || 1))} />
          </div>

          {/* Action type */}
          <div className="alert-form-row">
            <label>Action</label>
            <select value={formAction} onChange={e => setFormAction(e.target.value)}>
              {ACTION_TYPES.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
            </select>
          </div>

          {/* Action-specific params */}
          {formAction === 'led_color' && (
            <div className="alert-form-row">
              <label>Color</label>
              <div className="alert-color-picks">
                {LED_COLORS.map(c => (
                  <button key={c.id}
                    className={`alert-color-dot${formColor === c.id ? ' selected' : ''}`}
                    style={{ background: c.hex }}
                    title={c.label}
                    onClick={() => setFormColor(c.id)}
                  />
                ))}
              </div>
            </div>
          )}

          {formAction === 'led_rgb' && (
            <div className="alert-form-rgb">
              <div className="alert-form-row">
                <label>R</label>
                <input type="range" min="0" max="255" value={formR} onChange={e => setFormR(+e.target.value)} />
                <span className="alert-rgb-val">{formR}</span>
              </div>
              <div className="alert-form-row">
                <label>G</label>
                <input type="range" min="0" max="255" value={formG} onChange={e => setFormG(+e.target.value)} />
                <span className="alert-rgb-val">{formG}</span>
              </div>
              <div className="alert-form-row">
                <label>B</label>
                <input type="range" min="0" max="255" value={formB} onChange={e => setFormB(+e.target.value)} />
                <span className="alert-rgb-val">{formB}</span>
              </div>
              <div className="alert-rgb-preview" style={{ background: `rgb(${formR},${formG},${formB})` }} />
            </div>
          )}

          {formAction === 'buzzer_pattern' && (
            <div className="alert-form-pattern">
              <div className="alert-form-row">
                <label>On (ms)</label>
                <input type="number" min="50" max="2000" step="50" value={formOnMs}
                  onChange={e => setFormOnMs(+e.target.value)} />
              </div>
              <div className="alert-form-row">
                <label>Off (ms)</label>
                <input type="number" min="50" max="2000" step="50" value={formOffMs}
                  onChange={e => setFormOffMs(+e.target.value)} />
              </div>
              <div className="alert-form-row">
                <label>Repeats</label>
                <input type="number" min="1" max="20" value={formRepeats}
                  onChange={e => setFormRepeats(+e.target.value)} />
              </div>
            </div>
          )}

          {/* Form buttons */}
          <div className="alert-form-btns">
            <button className="alert-save-btn" onClick={addRule}>Add Rule</button>
            <button className="alert-cancel-btn" onClick={() => setShowForm(false)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}
