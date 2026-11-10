import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { Home, MessageCircle, CheckSquare, Bell, Wallet, Map, Bookmark, Settings, Compass, LogOut, Sparkles } from 'lucide-react';

const links = [
  {to:'/', label:'Home', icon:Home}, {to:'/chat', label:'AI Assistant', icon:MessageCircle},
  {to:'/vision', label:'Explore', icon:Compass}, {to:'/tasks', label:'Tasks', icon:CheckSquare},
  {to:'/reminders', label:'Reminders', icon:Bell}, {to:'/expenses', label:'Expenses', icon:Wallet},
  {to:'/travel', label:'Travel', icon:Map}, {to:'/saved', label:'Saved', icon:Bookmark},
];
export function AppShell() {
  const navigate = useNavigate();
  const logout = () => { localStorage.removeItem('warik_token'); navigate('/', {replace:true}); window.location.reload(); };
  return <div className="app-shell">
    <aside className="app-sidebar">
      <button className="app-brand" onClick={()=>navigate('/')}><span><Sparkles size={17}/></span> warik<span className="app-brand-ai">.ai</span></button>
      <div className="app-nav-label">WORKSPACE</div>
      <nav>{links.map(({to,label,icon:Icon})=><NavLink key={to} to={to} end={to==='/'} className={({isActive})=>`app-nav-link ${isActive?'active':''}`}><Icon size={18}/>{label}</NavLink>)}</nav>
      <div className="app-sidebar-bottom"><NavLink to="/settings" className="app-nav-link"><Settings size={18}/>Settings</NavLink><button className="app-nav-link" onClick={logout}><LogOut size={18}/>Sign out</button></div>
    </aside>
    <main className="app-main"><header className="app-topbar"><span>Personal workspace</span><span className="app-status"><i/> Assistant services</span></header><div className="app-page"><Outlet/></div></main>
  </div>;
}
