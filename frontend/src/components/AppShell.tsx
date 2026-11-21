import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity,
  ArrowUpRight,
  Bookmark,
  Bot,
  CalendarDays,
  CheckSquare,
  ChevronRight,
  CircleDot,
  Compass,
  Film,
  Home,
  LockKeyhole,
  LogOut,
  Map,
  MessageSquare,
  Plane,
  Settings,
  Sparkles,
  Train,
  Utensils,
  Wallet,
} from 'lucide-react';
import '../phase1.css';

const primaryLinks = [
  { to: '/', label: 'Overview', icon: Home, end: true },
  { to: '/chat', label: 'Command Center', icon: MessageSquare },
  { to: '/agent', label: 'Browser Agent', icon: Bot },
];

const workspaceLinks = [
  { to: '/travel', label: 'Travel', icon: Plane },
  { to: '/food', label: 'Places & Food', icon: Utensils },
  { to: '/tasks', label: 'Tasks', icon: CheckSquare },
  { to: '/reminders', label: 'Reminders', icon: CalendarDays },
  { to: '/expenses', label: 'Expenses', icon: Wallet },
  { to: '/saved', label: 'Saved', icon: Bookmark },
  { to: '/vision', label: 'Explore', icon: Compass },
];

const pageTitles: Record<string, string> = {
  '/': 'Overview',
  '/chat': 'Command Center',
  '/travel': 'Travel workspace',
  '/food': 'Places & food',
  '/tasks': 'Tasks',
  '/reminders': 'Reminders',
  '/expenses': 'Expenses',
  '/saved': 'Saved items',
  '/vision': 'Explore Warik',
  '/settings': 'Settings',
};

type QuickPrompt = { label: string; message: string; icon: typeof Plane; enabled: boolean };

const quickPrompts: QuickPrompt[] = [
  { label: 'Find a flight', message: 'Find flights from Delhi to Mumbai on 10 December 2026', icon: Plane, enabled: true },
  { label: 'Find a hotel', message: 'Find hotels in Goa for 10 to 12 December 2026 for two guests', icon: Map, enabled: true },
  { label: 'Explore movies', message: 'Show movies playing in Mumbai', icon: Film, enabled: false },
  { label: 'Explore trains', message: 'Find trains from Delhi to Mumbai', icon: Train, enabled: false },
];

function CommandInspector() {
  const navigate = useNavigate();

  const launchPrompt = (message: string) => {
    navigate('/', { state: { launchPrompt: message, launchAt: Date.now() } });
  };

  return (
    <aside className="wk-inspector" aria-label="Command center status and shortcuts">
      <section className="wk-inspector-section">
        <div className="wk-section-heading">
          <div>
            <span className="wk-kicker">WORKSPACE MAP</span>
            <h2>Connector hub</h2>
          </div>
          <span className="wk-live-indicator"><i /> ROUTES</span>
        </div>

        <div className="wk-connector-list">
          <div className="wk-connector-row">
            <span className="wk-connector-icon flight"><Plane size={15} /></span>
            <span className="wk-connector-copy"><strong>Flight discovery</strong><small>Backend provider route exists</small></span>
            <span className="wk-connector-state route">ROUTE</span>
          </div>
          <div className="wk-connector-row">
            <span className="wk-connector-icon hotel"><Map size={15} /></span>
            <span className="wk-connector-copy"><strong>Hotel discovery</strong><small>Backend provider route exists</small></span>
            <span className="wk-connector-state route">ROUTE</span>
          </div>
          <div className="wk-connector-row">
            <span className="wk-connector-icon movie"><Film size={15} /></span>
            <span className="wk-connector-copy"><strong>BookMyShow</strong><small>Movie discovery integration pending</small></span>
            <span className="wk-connector-state planned">NEXT</span>
          </div>
          <div className="wk-connector-row">
            <span className="wk-connector-icon train"><Train size={15} /></span>
            <span className="wk-connector-copy"><strong>RailYatri / IRCTC</strong><small>Authorized handoff required</small></span>
            <span className="wk-connector-state planned">NEXT</span>
          </div>
          <div className="wk-connector-row">
            <span className="wk-connector-icon vault"><LockKeyhole size={15} /></span>
            <span className="wk-connector-copy"><strong>Personal Vault</strong><small>Local profile UI pending</small></span>
            <span className="wk-connector-state planned">NEXT</span>
          </div>
        </div>
        <p className="wk-micro-note">Capability map only. These labels are not live provider health checks or proof of available inventory.</p>
      </section>

      <section className="wk-inspector-section wk-viewport-section">
        <div className="wk-section-heading">
          <div>
            <span className="wk-kicker">LOCAL PLAYWRIGHT</span>
            <h2>Browser viewport</h2>
          </div>
          <span className="wk-idle-pill"><i /> IDLE</span>
        </div>
        <div className="wk-browser-frame">
          <div className="wk-browser-toolbar">
            <span className="wk-browser-dots"><i /><i /><i /></span>
            <span className="wk-browser-address"><LockKeyhole size={10} /> localhost / browser-agent</span>
            <ArrowUpRight size={12} />
          </div>
          <div className="wk-browser-canvas">
            <div className="wk-browser-orbit orbit-one" />
            <div className="wk-browser-orbit orbit-two" />
            <div className="wk-browser-screen-icon"><Bot size={25} /></div>
            <strong>Awaiting a browser task</strong>
            <span>Live screenshots appear here when a real session is captured.</span>
            <div className="wk-browser-placeholder-tag"><CircleDot size={9} /> NO ACTIVE SESSION</div>
          </div>
        </div>
        <button className="wk-secondary-action" onClick={() => navigate('/agent')}>
          Open browser agent <ArrowUpRight size={14} />
        </button>
      </section>

      <section className="wk-inspector-section wk-trace-section">
        <details className="wk-trace-details">
          <summary>
            <span className="wk-trace-summary-icon"><Activity size={15} /></span>
            <span><strong>Execution trace</strong><small>How a request moves through Warik</small></span>
            <ChevronRight className="wk-trace-chevron" size={15} />
          </summary>
          <div className="wk-trace-list">
            <div><b>01</b><span><strong>Request received</strong><small>Natural-language message</small></span></div>
            <div><b>02</b><span><strong>Intent routed</strong><small>FastAPI orchestrator and tools</small></span></div>
            <div><b>03</b><span><strong>Evidence returned</strong><small>Provider output, when available</small></span></div>
            <div><b>04</b><span><strong>User reviews</strong><small>No booking or payment without approval</small></span></div>
          </div>
          <p className="wk-micro-note">Operational flow preview, not hidden model reasoning or live tool telemetry.</p>
        </details>
      </section>

      <section className="wk-quick-section">
        <div className="wk-section-heading"><div><span className="wk-kicker">QUICK LAUNCH</span><h2>Start with a prompt</h2></div></div>
        <div className="wk-quick-prompts">
          {quickPrompts.map((prompt) => {
            const Icon = prompt.icon;
            return <button key={prompt.label} disabled={!prompt.enabled} onClick={() => launchPrompt(prompt.message)}><Icon size={14} /><span>{prompt.label}</span>{prompt.enabled ? <ArrowUpRight size={12} /> : <small>SOON</small>}</button>;
          })}
        </div>
      </section>

      <div className="wk-approval-note"><LockKeyhole size={15} /><span><strong>You stay in control.</strong> Search results are not reservations. Review every handoff before proceeding.</span></div>
    </aside>
  );
}

export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const isCommandCenter = location.pathname === '/chat';
  const title = pageTitles[location.pathname] || 'Workspace';

  const logout = () => {
    localStorage.removeItem('warik_token');
    navigate('/', { replace: true });
    window.location.reload();
  };

  return (
    <div className="wk-shell">
      <aside className="wk-sidebar">
        <button className="wk-brand" onClick={() => navigate('/')} aria-label="Warik AI home">
          <span className="wk-brand-mark"><Sparkles size={17} /></span>
          <span>warik<span>.ai</span></span>
        </button>

        <div className="wk-nav-group">
          <span className="wk-nav-label">WORKSPACE</span>
          <nav className="wk-nav-list">
            {primaryLinks.map(({ to, label, icon: Icon, end }) => (
              <NavLink key={to} to={to} end={end} className={({ isActive }) => `wk-nav-link ${isActive ? 'active' : ''}`}>
                <Icon size={17} /><span>{label}</span>{to === '/chat' && <span className="wk-nav-hotkey">⌘ K</span>}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="wk-nav-group wk-workspace-group">
          <span className="wk-nav-label">YOUR TOOLS</span>
          <nav className="wk-nav-list">
            {workspaceLinks.map(({ to, label, icon: Icon }) => (
              <NavLink key={to} to={to} className={({ isActive }) => `wk-nav-link ${isActive ? 'active' : ''}`}>
                <Icon size={17} /><span>{label}</span>
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="wk-sidebar-bottom">
          <div className="wk-sidebar-trust"><span><LockKeyhole size={14} /></span><div><strong>Your decisions, always</strong><small>Review before actions</small></div></div>
          <NavLink to="/settings" className={({ isActive }) => `wk-nav-link ${isActive ? 'active' : ''}`}><Settings size={17} /><span>Settings</span></NavLink>
          <button className="wk-nav-link wk-logout" onClick={logout}><LogOut size={17} /><span>Sign out</span></button>
          <div className="wk-build-label">WARIK AI <span>LOCAL WORKSPACE</span></div>
        </div>
      </aside>

      <main className="wk-main">
        <header className="wk-topbar">
          <div className="wk-topbar-title"><span>WORKSPACE</span><ChevronRight size={13} /><strong>{title}</strong></div>
          <div className="wk-topbar-right"><span className="wk-runtime-label"><i /> LOCAL SESSION</span><span className="wk-topbar-divider" /><span className="wk-topbar-date">{new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}</span></div>
        </header>

        <div className={`wk-page ${isCommandCenter ? 'wk-page-command' : ''}`}>
          <div className="wk-outlet"><Outlet /></div>
          {isCommandCenter && <CommandInspector />}
        </div>
      </main>
    </div>
  );
}
