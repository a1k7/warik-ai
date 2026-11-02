import React from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { Home, MessageSquare, CheckSquare, Wallet, MapPin, Utensils, Bell, Brain, LogOut } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { clsx } from 'clsx';

const navItems = [
  { path: '/', icon: Home, label: 'Home' },
  { path: '/chat', icon: MessageSquare, label: 'AI Companion' },
  { path: '/tasks', icon: CheckSquare, label: 'Tasks' },
  { path: '/expenses', icon: Wallet, label: 'Expenses' },
  { path: '/travel', icon: MapPin, label: 'Travel' },
  { path: '/food', icon: Utensils, label: 'Food' },
  { path: '/reminders', icon: Bell, label: 'Reminders' },
  { path: '/memories', icon: Brain, label: 'Memories' },
];

export const Layout: React.FC = () => {
  const { logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="flex h-screen bg-ivory overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 bg-wine text-white flex flex-col hidden md:flex">
        <div className="p-6 border-b border-white/10">
          <h1 className="text-2xl font-bold tracking-tight text-rose">Warik AI</h1>
          <p className="text-xs text-white/50 mt-1">Your everyday companion</p>
        </div>
        
        <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) => clsx(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors text-sm font-medium",
                isActive ? "bg-burgundy text-white" : "text-white/70 hover:bg-white/5 hover:text-white"
              )}
            >
              <item.icon size={18} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-white/10">
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 px-3 py-2.5 w-full rounded-lg text-sm font-medium text-white/70 hover:bg-white/5 hover:text-white transition-colors"
          >
            <LogOut size={18} />
            Sign out
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col h-full overflow-hidden">
        {/* Mobile Header */}
        <header className="md:hidden bg-wine text-white p-4 flex justify-between items-center">
          <h1 className="text-xl font-bold text-rose">Warik AI</h1>
          <button onClick={handleLogout}><LogOut size={20} /></button>
        </header>
        
        <div className="flex-1 overflow-auto p-6 md:p-8">
          <div className="max-w-5xl mx-auto">
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  );
};