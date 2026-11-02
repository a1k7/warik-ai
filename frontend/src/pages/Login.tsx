import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authService } from '../services/api';

export const Login: React.FC = () => {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      if (isLogin) {
        await authService.login(email, password);
      } else {
        await authService.register(email, name, password);
      }
      // Force a reload so AuthContext picks up the new token
      window.location.href = '/';
    } catch (err: any) {
      // Handle FastAPI 422 validation errors gracefully
      const detail = err.response?.data?.detail;
      if (Array.isArray(detail)) {
        setError(`${detail[0].loc[1]}: ${detail[0].msg}`);
      } else if (typeof detail === 'string') {
        setError(detail);
      } else {
        setError('Authentication failed. Please check your credentials.');
      }
    }
  };

  return (
    <div className="min-h-screen bg-[#FAF7F3] flex items-center justify-center p-4">
      <div className="bg-white p-8 rounded-3xl shadow-xl w-full max-w-md border border-gray-100">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-[#4A1429]">Warik AI</h1>
          <p className="text-gray-500 mt-2">Your AI companion for everyday life.</p>
        </div>

        {error && <div className="bg-red-50 text-red-600 p-3 rounded-lg text-sm mb-4">{error}</div>}

        <form onSubmit={handleSubmit} className="space-y-4">
          {!isLogin && (
            <div>
              <label className="block text-sm font-medium text-[#30252A] mb-1">Name</label>
              <input
                type="text"
                required
                value={name}
                onChange={e => setName(e.target.value)}
                className="w-full bg-[#FAF7F3] border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#702D3C]/50"
              />
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-[#30252A] mb-1">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              className="w-full bg-[#FAF7F3] border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#702D3C]/50"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-[#30252A] mb-1">Password (min 8 characters)</label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="w-full bg-[#FAF7F3] border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#702D3C]/50"
            />
          </div>
          <button
            type="submit"
            className="w-full bg-[#702D3C] text-white py-3 rounded-xl font-medium hover:bg-[#4A1429] transition-colors mt-2"
          >
            {isLogin ? 'Sign In' : 'Create Account'}
          </button>
        </form>

        <div className="text-center mt-6">
          <button
            onClick={() => setIsLogin(!isLogin)}
            className="text-sm text-gray-500 hover:text-[#702D3C]"
          >
            {isLogin ? "Don't have an account? Sign up" : "Already have an account? Sign in"}
          </button>
        </div>
      </div>
    </div>
  );
};