import React from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  Home,
  MessageSquare,
  CheckSquare,
  Wallet,
  MapPin,
  Utensils,
  Bell,
  Brain,
  LogOut,
  Bookmark,
} from 'lucide-react';
import { clsx } from 'clsx';

const navItems = [
  { path: '/', icon: Home, label: 'Home' },
  { path: '/chat', icon: MessageSquare, label: 'AI Chat' },
  { path: '/saved', icon: Bookmark, label: 'My Saved' },
  { path: '/tasks', icon: CheckSquare, label: 'Tasks' },
  { path: '/expenses', icon: Wallet, label: 'Expenses' },
  { path: '/travel', icon: MapPin, label: 'Travel' },
  { path: '/food', icon: Utensils, label: 'Food' },
  { path: '/reminders', icon: Bell, label: 'Reminders' },
  { path: '/memories', icon: Brain, label: 'Memory' },
];

export const Layout: React.FC = () => {
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem('warik_token');
    navigate('/', { replace: true });
    window.location.reload();
  };

  return (
    <div className="flex h-[100dvh] bg-[#05030A] text-white overflow-hidden">
      <aside className="w-64 bg-jcard/30 border-r border-jprimary/10 flex-col hidden md:flex relative z-20">
        <div className="p-6 border-b border-jprimary/10">
          <h1 className="text-xl font-bold tracking-widest text-transparent bg-clip-text bg-gradient-to-r from-jprimary to-jsecondary">
            WARIK AI
          </h1>
        </div>

        <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-4 py-3 rounded-xl transition-all text-sm font-medium',
                  isActive
                    ? 'bg-jprimary/10 text-jsecondary'
                    : 'text-jmuted hover:bg-jcard hover:text-white',
                )
              }
            >
              <item.icon size={18} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-jprimary/10">
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 px-4 py-3 w-full rounded-xl text-sm font-medium text-jmuted hover:bg-red-500/10 hover:text-red-400 transition-colors"
          >
            <LogOut size={18} />
            Sign out
          </button>
        </div>
      </aside>

      <main className="flex-1 flex flex-col h-full relative z-10 overflow-y-auto">
        <div className="flex-1 p-4 md:p-8 pb-24 md:pb-8">
          <Outlet />
        </div>

        <nav className="md:hidden fixed bottom-0 w-full bg-[#05030A]/90 backdrop-blur-xl border-t border-jprimary/20 flex justify-around items-center pb-safe pt-2 z-50">
          {navItems.slice(0, 5).map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                clsx(
                  'flex flex-col items-center gap-1 p-2 w-16 transition-colors',
                  isActive ? 'text-jsecondary' : 'text-jmuted',
                )
              }
            >
              <item.icon
                size={20}
                className={clsx('transition-transform', 'active:scale-90')}
              />
              <span className="text-[10px] font-medium">{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </main>
    </div>
  );
};
