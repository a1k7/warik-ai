import React, { useEffect, useState } from 'react';
import { reminderService } from '../services/api';
import type { Reminder } from '../types';
import { Bell, CheckCircle2, Trash2 } from 'lucide-react';

export const Reminders: React.FC = () => {
  const [reminders, setReminders] = useState<Reminder[]>([]);

  const load = () => reminderService.list().then(setReminders);
  useEffect(() => { load(); }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-charcoal">Upcoming Reminders</h1>
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
        {reminders.length === 0 ? <p className="text-gray-500">No upcoming reminders. Try saying "Remind me to study at 7 PM"</p> : (
          <ul className="space-y-4">
            {reminders.map(rem => (
              <li key={rem.id} className="flex justify-between items-center border-b border-gray-50 pb-4 last:border-0 last:pb-0">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-ivory flex items-center justify-center text-burgundy">
                    <Bell size={18} />
                  </div>
                  <div>
                    <p className="font-medium text-charcoal">{rem.title}</p>
                    <p className="text-sm text-gray-500">{new Date(rem.remind_at).toLocaleString('en-IN')}</p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={async () => { await reminderService.complete(rem.id); load(); }} className="text-green-500 hover:text-green-700">
                    <CheckCircle2 size={20} />
                  </button>
                  <button onClick={async () => { await reminderService.delete(rem.id); load(); }} className="text-gray-300 hover:text-red-500">
                    <Trash2 size={20} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};