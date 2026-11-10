import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Moon, Sun, Palette, Type, Bell, ShieldCheck, Check } from 'lucide-react';

const palettes = [
  { name: 'Lavender', value: '#8b5cf6', soft: '#eee8ff' },
  { name: 'Ocean', value: '#4d8ee8', soft: '#e5f0ff' },
  { name: 'Rose', value: '#d76b9b', soft: '#ffedf4' },
  { name: 'Mint', value: '#329c83', soft: '#e5f7f1' },
];

export const Settings = () => {
  const navigate = useNavigate();
  const [dark, setDark] = useState(localStorage.getItem('warik_theme') === 'dark');
  const [accent, setAccent] = useState(localStorage.getItem('warik_accent') || '#8b5cf6');
  const [fontSize, setFontSize] = useState(localStorage.getItem('warik_font_size') || 'Regular');

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    document.documentElement.style.setProperty('--warik-accent', accent);
    localStorage.setItem('warik_theme', dark ? 'dark' : 'light');
    localStorage.setItem('warik_accent', accent);
    localStorage.setItem('warik_font_size', fontSize);
  }, [dark, accent, fontSize]);

  return <main className="settings-page">
    <header className="settings-header">
      <button className="back-button" onClick={() => navigate('/')}><ArrowLeft size={18}/> Back to home</button>
      <span className="overline">PERSONALISE YOUR EXPERIENCE</span>
      <h1>Settings</h1><p>Make Warik feel like yours.</p>
    </header>
    <section className="settings-card">
      <div className="settings-card-title"><span className="settings-icon"><Sun size={19}/></span><div><h2>Appearance</h2><p>Choose how Warik looks on your device.</p></div></div>
      <div className="setting-row"><div><strong>Dark mode</strong><small>Switch to a deeper, low-light interface.</small></div><button className={`toggle ${dark ? 'on' : ''}`} onClick={() => setDark(v => !v)} aria-label="Toggle dark mode"><span/></button></div>
      <div className="setting-row palette-row"><div><strong>Accent colour</strong><small>Choose a colour for highlights and controls.</small></div><div className="palette-options">{palettes.map(p => <button key={p.name} title={p.name} aria-label={p.name} className={accent === p.value ? 'selected' : ''} style={{'--swatch': p.value} as React.CSSProperties} onClick={() => setAccent(p.value)}>{accent === p.value && <Check size={15}/>}</button>)}</div></div>
      <div className="setting-row"><div><strong>Text size</strong><small>Adjust the reading size across the interface.</small></div><div className="font-options">{['Small','Regular','Large'].map(s => <button key={s} className={fontSize === s ? 'selected' : ''} onClick={() => setFontSize(s)}>{s}</button>)}</div></div>
    </section>
    <section className="settings-card">
      <div className="settings-card-title"><span className="settings-icon"><Bell size={19}/></span><div><h2>Notifications</h2><p>Manage how Warik keeps you updated.</p></div></div>
      <div className="setting-row"><div><strong>In-app notifications</strong><small>Updates about tasks and assistant activity.</small></div><span className="setting-status">Managed in app</span></div>
    </section>
    <section className="settings-card">
      <div className="settings-card-title"><span className="settings-icon"><ShieldCheck size={19}/></span><div><h2>Privacy & control</h2><p>Your data and actions remain under your control.</p></div></div>
      <div className="setting-row"><div><strong>Action approval</strong><small>Warik should ask before taking supported external actions.</small></div><span className="setting-status">Protected</span></div>
    </section>
    <p className="settings-footnote">Preferences are stored in this browser on this device.</p>
  </main>;
};
