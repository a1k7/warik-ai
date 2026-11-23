import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { CarFront, LogOut, ShieldCheck, Sparkles } from 'lucide-react';
import '../cab-workspace.css';

export function AppShell() {
  const navigate = useNavigate();
  const logout = () => {
    localStorage.removeItem('warik_token');
    localStorage.removeItem('warik_cab_conversation_id');
    navigate('/', { replace: true });
    window.location.reload();
  };
  return (
    <div className="cab-app-shell">
      <aside className="cab-sidebar">
        <button className="cab-brand" onClick={() => navigate('/')} aria-label="Warik cab home">
          <span className="cab-brand-mark"><Sparkles size={17} /></span><span>warik<span>.ai</span></span>
        </button>
        <span className="cab-sidebar-caption">MOBILITY WORKSPACE</span>
        <nav><NavLink to="/" end className={({ isActive }) => 'cab-sidebar-link' + (isActive ? ' active' : '')}><CarFront size={17} /><span>Find a ride</span></NavLink></nav>
        <div className="cab-sidebar-spacer" />
        <div className="cab-sidebar-trust"><ShieldCheck size={17} /><div><strong>You're in control</strong><small>Provider actions stay behind your approval.</small></div></div>
        <button className="cab-signout" onClick={logout}><LogOut size={16} /><span>Sign out</span></button>
        <div className="cab-sidebar-foot">WARIK MOBILITY<span>ONE JOB. DONE WELL.</span></div>
      </aside>
      <main className="cab-main">
        <header className="cab-topbar">
          <div className="cab-topbar-left"><span>WARIK MOBILITY</span><strong>/</strong><strong>RIDE SEARCH</strong></div>
          <div className="cab-topbar-right"><i /><span>SESSION READY</span><b>India · Local time</b></div>
        </header>
        <div className="cab-page"><Outlet /></div>
      </main>
    </div>
  );
}
