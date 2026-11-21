import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  CalendarDays,
  Film,
  Hotel,
  LockKeyhole,
  MapPin,
  Plane,
  Sparkles,
  Train,
  Wallet,
} from 'lucide-react';
import { AIOrb } from './AIOrb';
import { fetchCurrentUser } from './api';

const prompts = [
  { category: 'FLIGHTS', title: 'Find a flight', detail: 'Compare routes and schedules', icon: Plane, message: 'Find flights from Delhi to Mumbai on 10 December 2026', enabled: true },
  { category: 'STAYS', title: 'Find a hotel', detail: 'Explore stays for your dates', icon: Hotel, message: 'Find hotels in Goa for 10 to 12 December 2026 for two guests', enabled: true },
  { category: 'MOVIES', title: 'Explore movies', detail: 'Movie catalog integration next', icon: Film, message: 'Show movies playing in Mumbai', enabled: false },
  { category: 'TRAINS', title: 'Explore trains', detail: 'Authorized train handoff next', icon: Train, message: 'Find trains from Delhi to Mumbai', enabled: false },
];

export const Home = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [command, setCommand] = useState('');
  const [userName, setUserName] = useState('');

  useEffect(() => {
    let active = true;
    fetchCurrentUser()
      .then((user) => { if (active) setUserName(user.name?.trim() || ''); })
      .catch(() => { if (active) setUserName(''); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const prompt = location.state?.launchPrompt;
    if (typeof prompt === 'string' && prompt.trim()) {
      navigate('/chat', { state: { message: prompt, promptAt: location.state?.launchAt || Date.now() } });
    }
  }, [location.state, navigate]);

  const openChat = (message: string) => {
    navigate('/chat', { state: { message, promptAt: Date.now() } });
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!command.trim()) return;
    openChat(command.trim());
  };

  const firstName = userName.trim().split(/\s+/)[0] || 'there';
  const today = new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' });

  return (
    <div className="wk-home">
      <div className="wk-home-heading">
        <div><span className="wk-kicker"><i /> PERSONAL AI WORKSPACE</span><h1>Make room for <em>what matters.</em></h1><p>One place to plan, discover and move through everyday tasks.</p></div>
        <div className="wk-home-date"><CalendarDays size={14} />{today}</div>
      </div>

      <motion.section className="wk-hero-card" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, ease: 'easeOut' }}>
        <div className="wk-hero-copy">
          <span className="wk-hero-eyebrow"><Sparkles size={13} /> YOUR PERSONAL EXECUTION ASSISTANT</span>
          <h2>Good to see you,<br /><em>{firstName}.</em></h2>
          <p>Tell Warik what you want to get done. It can help search, organise and prepare the next step—while you stay in control.</p>
          <button className="wk-hero-cta" onClick={() => navigate('/chat')}>Open command center <ArrowRight size={15} /></button>
        </div>
        <div className="wk-hero-orb"><div className="wk-orb-glow" /><AIOrb state="idle" size="lg" /><span>READY WHEN YOU ARE</span></div>
        <div className="wk-hero-watermark">W</div>
      </motion.section>

      <section className="wk-home-command-section">
        <div className="wk-section-heading"><div><span className="wk-kicker">START WITH A REQUEST</span><h2>What can I help you with?</h2></div><span className="wk-command-hint"><Activity size={13} /> Natural language</span></div>
        <form className="wk-home-command" onSubmit={submit}>
          <span className="wk-command-spark"><Sparkles size={18} /></span>
          <input value={command} onChange={(event) => setCommand(event.target.value)} placeholder="e.g. Find me a flight from Delhi to Mumbai next Thursday…" aria-label="Tell Warik what you need" />
          <button type="submit" disabled={!command.trim()} aria-label="Send request"><ArrowRight size={17} /></button>
        </form>
        <div className="wk-command-disclaimer"><LockKeyhole size={12} /> You review provider results and approve actions. No booking or payment happens from a search request.</div>
      </section>

      <section className="wk-discovery-section">
        <div className="wk-section-heading"><div><span className="wk-kicker">DISCOVERY WORKSPACE</span><h2>Where should we start?</h2></div><button className="wk-text-link" onClick={() => navigate('/chat')}>View all capabilities <ArrowUpRight size={14} /></button></div>
        <div className="wk-service-grid">
          {prompts.map((item, index) => {
            const Icon = item.icon;
            return (
              <motion.button key={item.category} disabled={!item.enabled} className={`wk-service-card wk-service-${item.category.toLowerCase()} ${!item.enabled ? 'is-upcoming' : ''}`} onClick={() => item.enabled && openChat(item.message)} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.06 * index, duration: 0.35 }} whileHover={item.enabled ? { y: -4 } : undefined} whileTap={item.enabled ? { scale: 0.985 } : undefined}>
                <span className="wk-service-icon"><Icon size={19} /></span>
                <span className="wk-service-category">{item.category}</span>
                <strong>{item.title}</strong>
                <small>{item.detail}</small>
                {item.enabled ? <span className="wk-service-arrow"><ArrowUpRight size={15} /></span> : <span className="wk-service-coming">COMING NEXT</span>}
              </motion.button>
            );
          })}
        </div>
      </section>

      <section className="wk-home-bottom-grid">
        <div className="wk-home-info-card">
          <span className="wk-info-icon"><MapPin size={16} /></span><div><strong>Grounded in provider results</strong><p>Warik distinguishes live provider responses, external handoffs and demo content.</p></div>
        </div>
        <div className="wk-home-info-card">
          <span className="wk-info-icon"><Wallet size={16} /></span><div><strong>Approval before action</strong><p>Search is not a booking. Any consequential action requires your review.</p></div>
        </div>
      </section>

      <footer className="wk-home-footer"><span>WARIK AI <i>•</i> LOCAL WORKSPACE</span><span>Useful autonomy. Human control.</span></footer>
    </div>
  );
};
