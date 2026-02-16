import './KeyboardGuide.css';

export default function KeyboardGuide({ activeKeys }) {
  const KEY_VISUAL = {
    'w': 'w', 'ArrowUp': 'w',
    'a': 'a', 'ArrowLeft': 'a',
    's': 's', 'ArrowDown': 's',
    'd': 'd', 'ArrowRight': 'd',
  };

  const lit = new Set();
  for (const key of activeKeys) {
    const mapped = KEY_VISUAL[key] || KEY_VISUAL[key?.toLowerCase()];
    if (mapped) lit.add(mapped);
  }

  return (
    <div className="card">
      <div className="card-title"><span className="icon">⌨️</span> Keyboard Active</div>
      <div className="key-grid">
        <div className="key-cell empty" />
        <div className={`key-cell${lit.has('w') ? ' active' : ''}`}>W</div>
        <div className="key-cell empty" />
        <div className={`key-cell${lit.has('a') ? ' active' : ''}`}>A</div>
        <div className={`key-cell${lit.has('s') ? ' active' : ''}`}>S</div>
        <div className={`key-cell${lit.has('d') ? ' active' : ''}`}>D</div>
      </div>
    </div>
  );
}
