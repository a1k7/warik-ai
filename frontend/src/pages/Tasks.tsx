import React, { useEffect, useState } from 'react';
import { taskService } from '../services/api';
import type { Task } from '../types';
import { CheckCircle2, Circle, Trash2 } from 'lucide-react';

export const Tasks: React.FC = () => {
  const [tasks, setTasks] = useState<Task[]>([]);

  const load = () => taskService.list().then(setTasks);
  useEffect(() => { load(); }, []);

  const handleComplete = async (id: number) => {
    await taskService.complete(id);
    load();
  };
  const handleDelete = async (id: number) => {
    await taskService.delete(id);
    load();
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-charcoal">Your Tasks</h1>
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
        {tasks.length === 0 ? <p className="text-gray-500">No tasks yet. Ask Warik to add one!</p> : (
          <ul className="space-y-4">
            {tasks.map(task => (
              <li key={task.id} className="flex items-center justify-between group border-b border-gray-50 pb-4 last:border-0 last:pb-0">
                <div className="flex items-center gap-3">
                  <button onClick={() => handleComplete(task.id)}>
                    {task.completed ? <CheckCircle2 size={20} className="text-green-500" /> : <Circle size={20} className="text-gray-300 hover:text-burgundy" />}
                  </button>
                  <span className={task.completed ? "line-through text-gray-400" : "text-charcoal"}>{task.title}</span>
                </div>
                <button onClick={() => handleDelete(task.id)} className="text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity">
                  <Trash2 size={18} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};