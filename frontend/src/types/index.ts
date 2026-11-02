export interface User {
  id: number;
  email: string;
  name: string;
  created_at: string;
}

export interface Task {
  id: number;
  title: string;
  description?: string;
  due_date?: string;
  priority: 'low' | 'medium' | 'high';
  category?: string;
  completed: boolean;
}

export interface Expense {
  id: number;
  amount: string;
  category: string;
  description?: string;
  expense_date: string;
}

export interface Reminder {
  id: number;
  title: string;
  notes?: string;
  remind_at: string;
  completed: boolean;
}

export interface Memory {
  id: number;
  content: string;
  category?: string;
  created_at: string;
}

export interface TravelPlan {
  id: number;
  title: string;
  origin: string;
  destination: string;
  start_date?: string;
  end_date?: string;
  budget?: string;
}

export interface ToolCall {
  tool_name: string;
  args: Record<string, any>;
  success: boolean;
  message: string;
}

export interface AgentResponse {
  reply: string;
  tool_calls: ToolCall[];
  needs_confirmation: boolean;
  confirmation_token?: string;
  pending_tool?: string;
  pending_args?: Record<string, any>;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  agentData?: AgentResponse;
}