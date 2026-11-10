import {
  ArrowUpRight,
  Brain,
  Plane,
  Wallet,
  Workflow,
  Sparkles,
  ShieldCheck,
  Activity,
  Target,
  CheckCircle2,
  ChevronRight,
  MessageSquare,
  ArrowRight,
  Zap,
  Clock3,
  LockKeyhole,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const capabilities = [
  {
    number: '01',
    title: 'Travel Concierge',
    description: 'Plan, compare, coordinate and book trips.',
    icon: Plane,
    className: 'travel',
    visual: (
      <div className="travel-visual">
        <div className="travel-top">
          <span>YOUR NEXT JOURNEY</span>
          <span className="live-dot">● PLANNING</span>
        </div>
        <div className="travel-heading">Explore beyond<br />the ordinary.</div>
        <div className="travel-route">
          <div><span className="route-dot" /> Mumbai</div>
          <div className="route-line" />
          <div><span className="route-dot destination" /> Kerala</div>
        </div>
        <div className="travel-bottom">
          <span>Personalised itinerary</span>
          <span>Hotel discovery ↗</span>
        </div>
      </div>
    ),
  },
  {
    number: '02',
    title: 'Finance Assistant',
    description: 'Expenses, budgets, bills and financial planning.',
    icon: Wallet,
    className: 'finance',
    visual: (
      <div className="finance-visual">
        <div className="visual-label">MONTHLY FINANCIAL OVERVIEW</div>
        <div className="finance-total">₹24,850</div>
        <div className="visual-muted">Illustrative spending overview</div>
        <div className="finance-bars">
          {[48, 78, 55, 92, 63, 85, 43, 70, 58, 96, 64, 80].map((v, i) => (
            <span key={i} style={{ height: `${v}%` }} />
          ))}
        </div>
        <div className="finance-footer">
          <span>Budget tracking</span><span>AI insights ↗</span>
        </div>
      </div>
    ),
  },
  {
    number: '03',
    title: 'Personal Memory',
    description: 'Remember preferences, decisions and commitments.',
    icon: Brain,
    className: 'memory',
    visual: (
      <div className="memory-visual">
        <div className="memory-orb"><Brain size={32} /></div>
        <div className="memory-copy">
          <span className="visual-label">YOUR PERSONAL CONTEXT</span>
          <strong>Context that<br />stays with you.</strong>
          <span>Preferences · Decisions · Important moments</span>
        </div>
        <div className="memory-chip"><CheckCircle2 size={13} /> User-controlled memory</div>
      </div>
    ),
  },
  {
    number: '04',
    title: 'Action Engine',
    description: 'Execute tasks across supported applications with approval.',
    icon: Workflow,
    className: 'action',
    visual: (
      <div className="action-visual">
        <div className="visual-label">WORKFLOW EXECUTION</div>
        {[
          ['Understand request', 'Complete'],
          ['Check permissions', 'Complete'],
          ['Prepare action', 'Complete'],
          ['User approval', 'Required'],
        ].map(([label, status], i) => (
          <div className="action-row" key={label}>
            <span className="action-index">{`0${i + 1}`}</span>
            <span>{label}</span>
            <span className={status === 'Required' ? 'approval' : 'complete'}>
              {status}
            </span>
          </div>
        ))}
      </div>
    ),
  },
];

const priorities = [
  ['Reliability', 'Workflows complete successfully or explain exactly what failed.'],
  ['Persistent memory', 'User-approved preferences and decisions carry across conversations.'],
  ['Real execution', 'Move from recommendations to authorised actions.'],
  ['India-first integrations', 'UPI, Indian travel providers, local languages and regional services.'],
  ['Proactive assistance', 'Reminders, monitoring and follow-ups with user permission.'],
];

export const Vision = () => {
  const navigate = useNavigate();

  return (
    <main className="vision-page">
      <header className="vision-nav">
        <button className="vision-brand" onClick={() => navigate('/')}>
          <span className="brand-symbol"><Sparkles size={17} /></span>
          WARIK <span>AI</span>
        </button>
        <div className="vision-nav-right">
          <span className="system-status"><i /> SYSTEM ONLINE</span>
          <button className="vision-chat-button" onClick={() => navigate('/chat')}>
            Open assistant <ArrowUpRight size={15} />
          </button>
        </div>
      </header>

      <section className="vision-hero">
        <div className="eyebrow"><span /> THE PERSONAL EXECUTION OS</div>
        <h1>One assistant.<br /><span>Multiple execution systems.</span></h1>
        <p>
          Warik brings your personal context, everyday workflows and
          authorised actions together in one intelligent experience.
        </p>
        <div className="hero-actions">
          <button onClick={() => navigate('/chat')}>
            Start a conversation <ArrowRight size={16} />
          </button>
          <span><LockKeyhole size={13} /> You stay in control of every action.</span>
        </div>
        <div className="hero-orbit orbit-one" />
        <div className="hero-orbit orbit-two" />
      </section>

      <section className="capability-section">
        <div className="section-heading">
          <div>
            <span className="eyebrow">THE WARIK ECOSYSTEM</span>
            <h2>Built around your life.</h2>
          </div>
          <span className="section-count">04 SYSTEMS</span>
        </div>

        <div className="capability-grid">
          {capabilities.map((item) => (
            <article className={`capability-card ${item.className}`} key={item.title}>
              <div className="capability-meta">
                <span>{item.number} / CAPABILITY</span>
                <item.icon size={19} />
              </div>
              {item.visual}
              <div className="capability-info">
                <h3>{item.title}</h3>
                <p>{item.description}</p>
                <span className="capability-link">
                  Explore capability <ArrowUpRight size={14} />
                </span>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="principles-section">
        <div className="principles-intro">
          <span className="eyebrow">ENGINEERING PRINCIPLES</span>
          <h2>Intelligence is only<br />the beginning.</h2>
          <p>
            A useful assistant must do more than generate answers.
            It must be dependable, remember relevant context and act
            with permission.
          </p>
          <div className="principles-mark"><ShieldCheck size={20} /> TRUST BY DESIGN</div>
        </div>

        <div className="priority-list">
          {priorities.map(([title, description], i) => (
            <div className="priority-row" key={title}>
              <span className="priority-number">{`0${i + 1}`}</span>
              <div>
                <h3>{title}</h3>
                <p>{description}</p>
              </div>
              <ChevronRight size={17} />
            </div>
          ))}
        </div>
      </section>

      <section className="reliability-section">
        <div>
          <span className="eyebrow">THE RELIABILITY STANDARD</span>
          <h2>Prove it.<br /><span>Don't just promise it.</span></h2>
          <p>
            Our engineering target: 100 consecutive successful
            travel-planning tests across different destinations,
            budgets, dates and traveller counts, with no silent failures.
          </p>
        </div>
        <div className="reliability-card">
          <div className="reliability-icon"><Activity size={22} /></div>
          <span className="visual-label">VALIDATION TARGET</span>
          <strong>100</strong>
          <span className="reliability-subtitle">Consecutive successful test runs</span>
          <div className="reliability-progress"><span /></div>
          <span className="visual-muted">Target — not a claimed achievement</span>
        </div>
      </section>

      <section className="vision-cta">
        <div className="cta-icon"><Zap size={22} /></div>
        <div>
          <span className="eyebrow">YOUR NEXT STEP</span>
          <h2>Let's get something done.</h2>
          <p>Start with a request. Let Warik coordinate the work.</p>
        </div>
        <button onClick={() => navigate('/chat')}>
          Talk to Warik <ArrowUpRight size={16} />
        </button>
      </section>

      <footer className="vision-footer">
        <span>WARIK AI</span>
        <span>Personal Execution OS · Built by Warik Labs</span>
        <span><Clock3 size={12} /> Evolving continuously</span>
      </footer>
    </main>
  );
};
