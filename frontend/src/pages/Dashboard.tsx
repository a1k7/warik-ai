import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { taskService, expenseService } from '../services/api';
import type { Task, Expense } from '../types';
import { CheckCircle2, Circle, IndianRupee } from 'lucide-react';

export const Dashboard: React.FC = () => {
  const { user } = useAuth();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [totalSpent, setTotalSpent] = useState("0");

  useEffect(() => {
    const loadData = async () => {
      try {
        const [tsks, exps, summary] = await Promise.all([
          taskService.list(),
          expenseService.list(),
          expenseService.getSummary('today')
        ]);
        setTasks(tsks.slice(0, 5));
        setExpenses(exps.slice(0, 5));
        setTotalSpent(summary.total);
      } catch (err) {
        console.error("Dashboard load error", err);
      }
    };
    loadData();
  }, []);

  const today = new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' });

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-3xl font-bold text-charcoal">
          Good {new Date().getHours() < 12 ? 'morning' : new Date().getHours() < 18 ? 'afternoon' : 'evening'}, {user?.name.split(' ')[0]}
        </h1>
        <p className="text-gray-500 mt-1">{today}</p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Today's Tasks */}
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-charcoal">Today's Tasks</h2>
            <span className="text-xs font-medium bg-ivory text-burgundy px-2 py-1 rounded-md">{tasks.length} pending</span>
          </div>
          {tasks.length === 0 ? (
            <p className="text-sm text-gray-500">No tasks for today. You're all caught up!</p>
          ) : (
            <ul className="space-y-3">
              {tasks.map(task => (
                <li key={task.id} className="flex items-center gap-3 text-sm">
                  {task.completed ? <CheckCircle2 size={18} className="text-green-500" /> : <Circle size={18} className="text-gray-300" />}
                  <span className={task.completed ? "line-through text-gray-400" : "text-charcoal"}>{task.title}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Expense Summary */}
        <div className="bg-wine p-6 rounded-2xl shadow-sm text-white">
          <h2 className="text-lg font-semibold text-rose mb-4">Spent Today</h2>
          <div className="flex items-center gap-2 mb-6">
            <IndianRupee size={32} className="text-rose" />
            <span className="text-4xl font-bold">{totalSpent}</span>
          </div>
          
          <h3 className="text-sm font-medium text-white/60 mb-2">Recent Expenses</h3>
          <ul className="space-y-2">
            {expenses.length === 0 && <p className="text-sm text-white/50">No expenses recorded.</p>}
            {expenses.map(exp => (
              <li key={exp.id} className="flex justify-between text-sm">
                <span>{exp.category}</span>
                <span className="font-medium">₹{exp.amount}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
};