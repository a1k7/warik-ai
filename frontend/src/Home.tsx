import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowUpRight, Sparkles, Plane, CalendarDays, Wallet, Compass,
  FileText, ShieldCheck, BrainCircuit, MessageSquareText, Plus, ClipboardCheck,
  ArrowUp, Mic, Clock3, CheckCircle2, Utensils
} from 'lucide-react';
import { fetchCurrentUser } from './api';

const starters = [
  { label: 'Plan a trip', prompt: 'Help me plan a trip. Ask me for the details you need.', icon: Plane, tone: 'violet' },
  { label: 'Understand a document', prompt: 'I want to understand a document. Help me review it and extract the important points.', icon: FileText, tone: 'blue' },
  { label: 'Organise my day', prompt: 'Help me organise my day into a realistic plan.', icon: CalendarDays, tone: 'amber' },
  { label: 'Review my spending', prompt: 'Help me review my expenses and understand my spending.', icon: Wallet, tone: 'green' },
];

export const Home = () => {
  const navigate = useNavigate();
  const [command, setCommand] = useState('');
  const [userName, setUserName] = useState('');

  useEffect(() => {
    let active = true;
    fetchCurrentUser()
      .then((user) => { if (active) setUserName(user.name?.trim() || ''); })
      .catch((error) => console.error('Unable to load authenticated user profile:', error));
    return () => { active = false; };
  }, []);

  const openChat = (message?: string) => {
    navigate('/chat', message ? { state: { message } } : undefined);
  };
  const openVoice = () => navigate('/chat', { state: { openVoice: true } });
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (command.trim()) openChat(command.trim());
  };
  const firstName = userName.split(/\s+/)[0] || 'there';

  return (
    <div className="warik-home">
      <header className="wh-top">
        <div>
          <div className="wh-kicker"><span className="wh-live" /> YOUR PERSONAL AI WORKSPACE</div>
          <h1>Good to see you, <span>{firstName}.</span></h1>
          <p>Bring a question, a plan, a document or a task. Let's move it forward.</p>
        </div>
        <button className="wh-new-chat" onClick={() => openChat()}><Plus size={16}/> New conversation</button>
      </header>

      <section className="wh-command">
        <div className="wh-command-orb"><Sparkles size={21}/></div>
        <div className="wh-command-copy">
          <span>WARIK ASSISTANT</span>
          <strong>What would you like to work on?</strong>
          <small>Ask naturally. Warik can reason, use supported tools and ask before taking actions.</small>
        </div>
        <form className="wh-composer" onSubmit={submit}>
          <input value={command} onChange={event => setCommand(event.target.value)} placeholder="Ask Warik anything…" aria-label="Message Warik" />
          <button type="button" aria-label="Open voice mode" title="Open Warik voice mode" onClick={openVoice} className="wh-mic"><Mic size={18}/></button>
          <button type="submit" disabled={!command.trim()} aria-label="Send message"><ArrowUp size={19}/></button>
        </form>
        <div className="wh-command-foot"><span><ShieldCheck size={13}/> Actions require your approval</span><span><Sparkles size={13}/> Context-aware assistance</span></div>
      </section>

      <section className="wh-section">
        <div className="wh-section-head"><div><span>GET STARTED</span><h2>Make something happen</h2></div><button onClick={() => openChat('What can you help me with?')}>Explore capabilities <ArrowUpRight size={15}/></button></div>
        <div className="wh-starters">
          {starters.map(({label,prompt,icon:Icon,tone}) => (
            <button key={label} className="wh-starter" onClick={() => openChat(prompt)}>
              <span className={`wh-starter-icon ${tone}`}><Icon size={19}/></span>
              <strong>{label}</strong>
              <span className="wh-starter-arrow"><ArrowUpRight size={16}/></span>
            </button>
          ))}
        </div>
      </section>

      <section className="wh-lower">
        <div className="wh-work-panel">
          <div className="wh-section-head"><div><span>YOUR WORKSPACE</span><h2>One assistant. Connected workflows.</h2></div></div>
          <div className="wh-work-grid">
            <button onClick={() => navigate('/ledger')}><span className="wh-mini-icon"><ClipboardCheck size={17}/></span><span><strong>Action Ledger</strong><small>Track commitments through verified outcomes</small></span><ArrowUpRight size={15}/></button>
            <button onClick={() => navigate('/tasks')}><span className="wh-mini-icon"><CheckCircle2 size={17}/></span><span><strong>Tasks & reminders</strong><small>Keep plans and follow-ups moving</small></span><ArrowUpRight size={15}/></button>
            <button onClick={() => navigate('/travel')}><span className="wh-mini-icon"><Compass size={17}/></span><span><strong>Travel planning</strong><small>Turn trip ideas into itineraries</small></span><ArrowUpRight size={15}/></button>
            <button onClick={() => navigate('/expenses')}><span className="wh-mini-icon"><Wallet size={17}/></span><span><strong>Personal finances</strong><small>Track expenses and budgets</small></span><ArrowUpRight size={15}/></button>
            <button onClick={() => navigate('/food')}><span className="wh-mini-icon"><Utensils size={17}/></span><span><strong>Food discovery</strong><small>Find options and connected services</small></span><ArrowUpRight size={15}/></button>
          </div>
        </div>
        <aside className="wh-trust-panel">
          <div className="wh-trust-icon"><BrainCircuit size={20}/></div>
          <span className="wh-trust-label">BUILT AROUND YOU</span>
          <h3>Useful context.<br/>Clear control.</h3>
          <p>Warik is designed to carry relevant context between conversations while keeping important actions under your control.</p>
          <button onClick={() => navigate('/settings')}>Manage your preferences <ArrowUpRight size={14}/></button>
          <div className="wh-trust-divider"/>
          <div className="wh-trust-note"><Clock3 size={14}/> Review actions and outcomes in your conversations.</div>
        </aside>
      </section>
      <footer className="wh-footer"><span>WARIK AI</span><span>Think clearly. Act deliberately.</span></footer>
    </div>
  );
};
