import { useState } from 'react';
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
} from 'react-router-dom';

import { Home } from './Home';
import { Chat } from './Chat';
import { Vision } from './pages/Vision';
import { Saved } from './pages/Saved';
import { Settings } from './pages/Settings';
import { Tasks } from './pages/Tasks';
import { Reminders } from './pages/Reminders';
import { Expenses } from './pages/Expenses';
import { Travel } from './pages/Travel';
import { Food } from './pages/Food';

import { AppShell } from './components/AppShell';
import { login, register } from './api';

function LoginScreen({ onLogin }: { onLogin: () => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');

    try {
      if (mode === 'register') {
        await register(email, name, password);
      } else {
        await login(email, password);
      }

      onLogin();
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ||
        'Unable to authenticate. Check your details and backend connection.'
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="login-mark">✦</div>
        <h1 className="login-brand">warik<span>.ai</span></h1>
        <p className="login-subtitle">
          Your personal execution assistant.
        </p>

        <form onSubmit={submit} className="login-form">
          {mode === 'register' && (
            <label>
              Name
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="name"
              />
            </label>
          )}

          <label>
            Email
            <input
              required
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
          </label>

          <label>
            Password
            <input
              required
              type="password"
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={
                mode === 'register' ? 'new-password' : 'current-password'
              }
            />
          </label>

          {error && <p className="inline-error">{error}</p>}

          <button className="login-button" disabled={busy}>
            {busy
              ? 'Please wait…'
              : mode === 'register'
                ? 'Create account'
                : 'Sign in'}
          </button>
        </form>

        <button
          className="auth-switch"
          onClick={() => {
            setMode(mode === 'login' ? 'register' : 'login');
            setError('');
          }}
        >
          {mode === 'login'
            ? "Don't have an account? Create one"
            : 'Already registered? Sign in'}
        </button>
      </div>
    </div>
  );
}

function App() {
  const [loggedIn, setLoggedIn] = useState(
    !!localStorage.getItem('warik_token')
  );

  return (
    <BrowserRouter>
      {!loggedIn ? (
        <LoginScreen onLogin={() => setLoggedIn(true)} />
      ) : (
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<Home />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/vision" element={<Vision />} />
            <Route path="/tasks" element={<Tasks />} />
            <Route path="/reminders" element={<Reminders />} />
            <Route path="/expenses" element={<Expenses />} />
            <Route path="/travel" element={<Travel />} />
            <Route path="/food" element={<Food />} />
            <Route path="/saved" element={<Saved />} />
            <Route path="/settings" element={<Settings />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      )}
    </BrowserRouter>
  );
}

export default App;
