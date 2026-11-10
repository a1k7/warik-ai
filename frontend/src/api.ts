import axios from 'axios';

const configuredBase = import.meta.env.VITE_API_BASE_URL as string | undefined;
export const api = axios.create({ baseURL: configuredBase || 'http://127.0.0.1:8000/api', timeout: 30000 });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('warik_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
api.interceptors.response.use((response) => response, (error) => {
  if (error.response?.status === 401) {
    localStorage.removeItem('warik_token');
    if (window.location.pathname !== '/') window.location.assign('/');
  }
  return Promise.reject(error);
});

export const login = async (email: string, password: string) => {
  const res = await api.post('/auth/login', { email, password });
  localStorage.setItem('warik_token', res.data.access_token);
  return res.data;
};
export const register = async (email: string, name: string, password: string) => {
  const res = await api.post('/auth/register', { email, name, password });
  localStorage.setItem('warik_token', res.data.access_token);
  return res.data;
};
export const saveFavoriteRestaurant = async (name: string, location: string) => (await api.post('/food/favorites', { name, location })).data;

export const fetchConversations = async () => (await api.get('/conversations')).data;
export const createConversation = async () => (await api.post('/conversations', { title: 'New Chat' })).data;
export const fetchConversationDetail = async (id: number) => (await api.get(`/conversations/${id}`)).data;
export const deleteConversation = async (id: number) => { await api.delete(`/conversations/${id}`); };
export const updateConversationTitle = async (id: number, title: string) => { await api.patch(`/conversations/${id}`, { title }); };
export const sendMessageInConversation = async (id: number, text: string) => {
  const response = await api.post(
    `/conversations/${id}/message`,
    { text },
    { timeout: 240000 }
  );
  return response.data;
};
export const uploadDocument = async (file: File, conversationId?: number) => {
  const form = new FormData(); form.append('file', file);
  if (conversationId) form.append('conversation_id', String(conversationId));
  return (await api.post('/documents/upload', form)).data as { document_id: number; filename: string; page_count: number; char_count: number; preview: string };
};
export const listDocuments = async (conversationId?: number) => (await api.get('/documents', { params: conversationId ? { conversation_id: conversationId } : {} })).data;
export const deleteDocument = async (documentId: number) => { await api.delete(`/documents/${documentId}`); };
export const sendMessageWithDocument = async (
  convId: number,
  text: string,
  documentId?: number
) => {
  const response = await api.post(
    `/conversations/${convId}/message`,
    {
      text,
      document_id: documentId,
    },
    { timeout: 240000 }
  );
  return response.data;
};

export type TaskPriority = 'low' | 'medium' | 'high';
export interface TaskItem { id:number; title:string; description?:string|null; due_date?:string|null; priority:TaskPriority; category?:string|null; completed:boolean; completed_at?:string|null; created_at:string; updated_at:string; }
export interface ReminderItem { id:number; title:string; notes?:string|null; remind_at:string; completed:boolean; completed_at?:string|null; created_at:string; updated_at:string; }
export interface ExpenseItem { id:number; amount:string|number; currency:string; category:string; description?:string|null; expense_date:string; created_at:string; updated_at:string; }
export interface TravelStop { id?:number; name:string; notes?:string|null; arrival?:string|null; departure?:string|null; estimated_cost?:string|number|null; order_index?:number; }
export interface TravelPlan { id:number; title:string; origin:string; destination:string; start_date?:string|null; end_date?:string|null; travellers:number; budget?:string|number|null; currency:string; notes?:string|null; stops:TravelStop[]; created_at:string; updated_at:string; }

export const tasksApi = {
  list: async () => (await api.get<TaskItem[]>('/tasks/')).data,
  create: async (payload: Partial<TaskItem>) => (await api.post<TaskItem>('/tasks/', payload)).data,
  update: async (id:number, payload: Partial<TaskItem>) => (await api.put<TaskItem>(`/tasks/${id}`, payload)).data,
  complete: async (id:number) => (await api.post<TaskItem>(`/tasks/${id}/complete`)).data,
  remove: async (id:number) => { await api.delete(`/tasks/${id}`); },
};
export const remindersApi = {
  list: async (completed?: boolean) => (await api.get<ReminderItem[]>('/reminders/', { params: completed === undefined ? {} : { completed } })).data,
  create: async (payload: {title:string; notes?:string; remind_at:string}) => (await api.post<ReminderItem>('/reminders/', payload)).data,
  update: async (id:number, payload: Partial<ReminderItem>) => (await api.put<ReminderItem>(`/reminders/${id}`, payload)).data,
  complete: async (id:number) => (await api.post<ReminderItem>(`/reminders/${id}/complete`)).data,
  remove: async (id:number) => { await api.delete(`/reminders/${id}`); },
};
export const expensesApi = {
  list: async () => (await api.get<ExpenseItem[]>('/expenses/')).data,
  create: async (payload: {amount:number; category:string; description?:string; expense_date?:string; currency?:string}) => (await api.post<ExpenseItem>('/expenses/', payload)).data,
  update: async (id:number, payload: Partial<ExpenseItem>) => (await api.put<ExpenseItem>(`/expenses/${id}`, payload)).data,
  remove: async (id:number) => { await api.delete(`/expenses/${id}`); },
  summary: async (period:'today'|'week'|'month'='month') => (await api.get('/expenses/summary', { params:{period} })).data,
  budgetStatus: async () => (await api.get('/expenses/budget-status')).data,
};
export const travelApi = {
  list: async () => (await api.get<TravelPlan[]>('/travel/')).data,
  create: async (payload: Record<string, unknown>) => (await api.post<TravelPlan>('/travel/', payload)).data,
  update: async (id:number, payload: Record<string, unknown>) => (await api.put<TravelPlan>(`/travel/${id}`, payload)).data,
  remove: async (id:number) => { await api.delete(`/travel/${id}`); },
};
