import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Sparkles, Plus, Mic, ArrowUp, Utensils, Coffee, Pizza, Map,
  MessageCircle, Compass, Bookmark, Settings, Menu, X, Plane,
  Wallet, CalendarDays, ChevronRight, Sun
} from 'lucide-react';
import { AIOrb } from './AIOrb';

const prompts = [
  { text: 'Plan a weekend in Goa', icon: Plane, tag: 'TRAVEL' },
  { text: 'Help me organise my day', icon: CalendarDays, tag: 'PLANNING' },
  { text: 'Find great cafes nearby', icon: Coffee, tag: 'DISCOVERY' },
  { text: 'Track my spending', icon: Wallet, tag: 'FINANCE' },
];

export const Home = () => {
  const navigate = useNavigate();
  const [command, setCommand] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!command.trim()) return;
    navigate('/chat', { state: { message: command } });
  };

  return (
    <div className="home-shell">
      <aside className={`home-sidebar ${menuOpen ? 'is-open' : ''}`}>
        <div className="home-brand"><span className="brand-mark"><Sparkles size={17}/></span><span>warik<span className="brand-ai">.ai</span></span></div>
        <div className="sidebar-caption">YOUR WORKSPACE</div>
        <nav className="home-nav">
          <button className="active" onClick={() => navigate('/')}><Sun size={18}/> Home</button>
          <button onClick={() => navigate('/chat')}><MessageCircle size={18}/> AI Assistant</button>
          <button onClick={() => navigate('/vision')}><Compass size={18}/> Explore Warik</button>
          <button onClick={() => navigate('/chat', { state: { message: 'Show my saved places and trips' } })}><Bookmark size={18}/> Saved</button>
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-tip"><Sparkles size={16}/><span>One place for the things that move your day forward.</span></div>
          <button className="sidebar-settings" onClick={() => navigate('/settings')}><Settings size={18}/> Preferences</button>
        </div>
      </aside>

      <main className="home-main">
        <header className="home-topbar">
          <button className="mobile-menu" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X/> : <Menu/>}</button>
          <div className="breadcrumb">Workspace <ChevronRight size={14}/> <strong>Home</strong></div>
          <button className="profile-pill" onClick={() => navigate('/settings')}><span className="profile-avatar">A</span><span>Akhilesh</span></button>
        </header>

        <section className="home-content">
          <div className="home-greeting">
            <div className="greeting-copy">
              <span className="overline"><span className="online-dot"/> YOUR PERSONAL AI COMPANION</span>
              <h1>Welcome,<br/><em>Akhilesh.</em></h1>
              <p>What would you like to make happen today?</p>
            </div>
            <div className="greeting-date">{new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' })}</div>
          </div>

          <div className="assistant-stage">
            <div className="stage-glow"/>
            <AIOrb state="idle" size="lg"/>
            <div className="orb-caption"><span className="pulse-dot"/> WARIK IS HERE</div>
            <h2>I'm listening.</h2>
            <p>Ask me anything, or choose a place to start.</p>
          </div>

          <div className="prompt-section">
            <div className="section-label"><span>QUICK START</span><span>CHOOSE A PROMPT</span></div>
            <div className="prompt-grid">
              {prompts.map((p) => <button className="prompt-card" key={p.text} onClick={() => navigate('/chat', { state: { message: p.text } })}>
                <span className="prompt-icon"><p.icon size={19}/></span>
                <span className="prompt-meta">{p.tag}</span>
                <strong>{p.text}</strong>
                <ChevronRight className="prompt-arrow" size={17}/>
              </button>)}
            </div>
          </div>

          <form onSubmit={submit} className="home-composer">
            <button type="button" className="composer-add" aria-label="New chat" onClick={() => navigate('/chat')}><Plus size={20}/></button>
            <input value={command} onChange={e => setCommand(e.target.value)} placeholder="Message Warik..."/>
            <button type="button" className="composer-mic" aria-label="Voice assistant" onClick={() => navigate('/chat')}><Mic size={19}/></button>
            <button type="submit" className="composer-send" disabled={!command.trim()} aria-label="Send message"><ArrowUp size={19}/></button>
          </form>
          <div className="composer-note">Warik can make mistakes. Review important information before acting.</div>

          <div className="home-footer"><span>WARIK AI</span><span>Thoughtful assistance. Your decisions.</span></div>
        </section>
      </main>
    </div>
  );
};
