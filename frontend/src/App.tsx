import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Layout } from './components/Layout';
import { Dashboard } from './pages/Dashboard';
import { Chat } from './pages/Chat';
import { Login } from './pages/Login';
import { Tasks } from './pages/Tasks';
import { Expenses } from './pages/Expenses';
import { Reminders } from './pages/Reminders';
import { Memories } from './pages/Memories';
import { Travel } from './pages/Travel';
import { Food } from './pages/Food';

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const { user, loading } = useAuth();
  
  if (loading) return <div className="min-h-screen flex items-center justify-center bg-ivory text-burgundy">Loading...</div>;
  if (!user) return <Navigate to="/login" replace />;
  
  return <>{children}</>;
};

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          
          <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
            <Route index element={<Dashboard />} />
            <Route path="chat" element={<Chat />} />
            <Route path="tasks" element={<Tasks />} />
            <Route path="expenses" element={<Expenses />} />
            <Route path="travel" element={<Travel />} />
            <Route path="food" element={<Food />} />
            <Route path="reminders" element={<Reminders />} />
            <Route path="memories" element={<Memories />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;