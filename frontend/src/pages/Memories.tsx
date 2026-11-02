import React, { useEffect, useState } from 'react';
import { memoryService } from '../services/api';
import type { Memory } from '../types';
import { Brain, Trash2 } from 'lucide-react';

export const Memories: React.FC = () => {
  const [memories, setMemories] = useState<Memory[]>([]);

  const load = () => memoryService.list().then(setMemories);
  useEffect(() => { load(); }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-charcoal">What Warik Remembers</h1>
      <p className="text-gray-500 text-sm">These are facts you explicitly asked Warik to save. You can delete them at any time.</p>
      
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
        {memories.length === 0 ? <p className="text-gray-500">Warik hasn't saved any memories yet. Try saying "Remember that I prefer travelling by train"</p> : (
          <ul className="space-y-4">
            {memories.map(mem => (
              <li key={mem.id} className="flex justify-between items-center border-b border-gray-50 pb-4 last:border-0 last:pb-0">
                <div className="flex items-center gap-3">
                  <Brain size={18} className="text-burgundy" />
                  <p className="text-charcoal">{mem.content}</p>
                </div>
                <button onClick={async () => { await memoryService.delete(mem.id); load(); }} className="text-gray-300 hover:text-red-500">
                  <Trash2 size={16} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};