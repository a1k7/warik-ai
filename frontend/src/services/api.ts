import axios from 'axios';
import type{ User, Task, Expense, AgentResponse, Reminder, Memory, TravelPlan, ChatMessage } from '../types';

const api = axios.create({
  baseURL: 'http://127.0.0.1:8000/api',
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('warik_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const authService = {
  login: async (email: string, password: string) => {
    const res = await api.post<{ access_token: string }>('/auth/login', { email, password });
    localStorage.setItem('warik_token', res.data.access_token);
    return res.data;
  },
  register: async (email: string, name: string, password: string) => {
    const res = await api.post<{ access_token: string }>('/auth/register', { email, name, password });
    localStorage.setItem('warik_token', res.data.access_token);
    return res.data;
  },
  getMe: async () => {
    const res = await api.get<User>('/auth/me');
    return res.data;
  },
  logout: () => {
    localStorage.removeItem('warik_token');
  }
};

export const agentService = {
  sendMessage: async (text: string) => {
    const res = await api.post<AgentResponse>('/agent/message', { text });
    return res.data;
  },
  confirmAction: async (token: string) => {
    const res = await api.post<AgentResponse>('/agent/confirm', { confirmation_token: token });
    return res.data;
  }
};

export const voiceService = {
  sendVoiceMessage: async (audioBlob: Blob, durationSeconds: number) => {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');
    formData.append('language_code', 'en-IN');
    formData.append('duration_seconds', durationSeconds.toString());
    
    const res = await api.post<AgentResponse>('/voice/message', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return res.data;
  }
};

export const taskService = {
  list: async () => {
    const res = await api.get<Task[]>('/tasks/');
    return res.data;
  },
  create: async (data: { title: string; priority: string }) => {
    const res = await api.post<Task>('/tasks/', data);
    return res.data;
  },
  complete: async (id: number) => {
    const res = await api.post<Task>(`/tasks/${id}/complete`);
    return res.data;
  },
  delete: async (id: number) => {
    await api.delete(`/tasks/${id}`);
  }
};

export const expenseService = {
  list: async () => {
    const res = await api.get<Expense[]>('/expenses/');
    return res.data;
  },
  getSummary: async (period: string) => {
    const res = await api.get(`/expenses/summary?period=${period}`);
    return res.data;
  },
  delete: async (id: number) => {
    await api.delete(`/expenses/${id}`);
  }
};

export const reminderService = {
  list: async () => {
    const res = await api.get<Reminder[]>('/reminders/');
    return res.data;
  },
  complete: async (id: number) => {
    const res = await api.post<Reminder>(`/reminders/${id}/complete`);
    return res.data;
  },
  delete: async (id: number) => {
    await api.delete(`/reminders/${id}`);
  }
};

export const memoryService = {
  list: async () => {
    const res = await api.get<Memory[]>('/memories/');
    return res.data;
  },
  delete: async (id: number) => {
    await api.delete(`/memories/${id}`);
  }
};

export const travelService = {
  list: async () => {
    const res = await api.get<TravelPlan[]>('/travel/');
    return res.data;
  }
};

export const foodService = {
  search: async (query: string) => {
    // Save query to a mock location and preference for the backend
    const res = await api.post<{ disclaimer: string; external_links: Record<string, string> }>('/food/search', { location: query });
    return res.data;
  }
};