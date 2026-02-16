import { useState, useCallback } from 'react';
import './DetectionPanel.css';

export default function DetectionPanel({ emit, detectionState }) {
  const [classes, setClasses] = useState(
    (detectionState?.classes || ['person', 'car', 'dog', 'cat', 'bottle']).join(', ')
  );
  const [confidence, setConfidence] = useState(
    detectionState?.confidence ?? 0.35
  );

  const toggleDetection = useCallback((enabled) => {
    emit('detection_toggle', { enabled });
  }, [emit]);

  const handleConfidenceChange = useCallback((e) => {
    const val = parseInt(e.target.value) / 100;
    setConfidence(val);
    emit('detection_config', { confidence: val });
  }, [emit]);

  const handleClassesSubmit = useCallback(() => {
    const list = classes.split(',').map(c => c.trim()).filter(c => c);
    emit('detection_config', { classes: list });
  }, [emit, classes]);

  const detections = detectionState?.detections || [];
  const yoloAvailable = detectionState?.yolo_available ?? false;
  const enabled = detectionState?.enabled ?? false;

  // Count detections by class
  const counts = {};
  detections.forEach(d => {
    counts[d.class] = (counts[d.class] || 0) + 1;
  });

  return (
    <div className="card detection-panel">
      <div className="card-title"><span className="icon">🔍</span> YOLO Detection</div>

      {/* Status indicator */}
      <div className={`det-status-badge ${yoloAvailable ? 'available' : 'unavailable'}`}>
        {yoloAvailable ? '✅ Model loaded' : '⚠️ YOLO unavailable'}
      </div>

      {/* Toggle */}
      <div className="det-toggle-row">
        <label>Enable Detection</label>
        <label className="toggle">
          <input type="checkbox"
            checked={enabled}
            onChange={(e) => toggleDetection(e.target.checked)}
            disabled={!yoloAvailable}
          />
          <span className="toggle-slider" />
        </label>
      </div>

      {/* Confidence */}
      <div className="slider-group">
        <div className="slider-label">
          <span>Confidence Threshold</span>
          <span className="slider-value">{confidence.toFixed(2)}</span>
        </div>
        <input type="range" min="5" max="100"
          value={Math.round(confidence * 100)}
          onChange={handleConfidenceChange} />
      </div>

      {/* Classes */}
      <div className="slider-group">
        <div className="slider-label"><span>Detection Classes</span></div>
        <div className="det-classes-row">
          <input type="text"
            className="det-classes-input"
            value={classes}
            onChange={(e) => setClasses(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleClassesSubmit(); } }}
            placeholder="person, car, dog..."
          />
          <button className="det-apply-btn" onClick={handleClassesSubmit}>
            Apply
          </button>
        </div>
      </div>

      {/* Results */}
      {enabled && (
        <div className="det-results">
          {Object.keys(counts).length > 0 ? (
            <div className="det-results-grid">
              {Object.entries(counts).map(([cls, count]) => (
                <div key={cls} className="det-result-item">
                  <span className="det-class-name">{cls}</span>
                  <span className="det-class-count">{count}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="det-no-results">No detections</div>
          )}
        </div>
      )}
    </div>
  );
}
