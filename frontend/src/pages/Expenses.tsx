import React, { useEffect, useState } from 'react';
import { expenseService } from '../services/api';
import type { Expense } from '../types';
import { Trash2 } from 'lucide-react';

export const Expenses: React.FC = () => {
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [summary, setSummary] = useState<any>({ total: "0" });

  const load = async () => {
    const [e, s] = await Promise.all([expenseService.list(), expenseService.getSummary('month')]);
    setExpenses(e);
    setSummary(s);
  };

  useEffect(() => { load(); }, []);

  const handleDelete = async (id: number) => {
    await expenseService.delete(id);
    load();
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-charcoal">Expenses</h1>
      
      <div className="bg-wine rounded-2xl p-6 text-white flex justify-between items-center">
        <div>
          <p className="text-rose text-sm font-medium mb-1">Total Spent This Month</p>
          <h2 className="text-3xl font-bold">₹{summary.total}</h2>
        </div>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
        <h3 className="font-semibold text-charcoal mb-4">Recent Transactions</h3>
        {expenses.length === 0 ? <p className="text-gray-500">No expenses recorded. Ask Warik "I spent ₹250 on lunch"</p> : (
          <ul className="space-y-4">
            {expenses.map(exp => (
              <li key={exp.id} className="flex justify-between items-center border-b border-gray-50 pb-4 last:border-0 last:pb-0">
                <div>
                  <p className="font-medium text-charcoal">{exp.category}</p>
                  <p className="text-sm text-gray-500">{exp.expense_date} {exp.description && `• ${exp.description}`}</p>
                </div>
                <div className="flex items-center gap-4">
                  <span className="font-bold text-charcoal">₹{exp.amount}</span>
                  <button onClick={() => handleDelete(exp.id)} className="text-gray-300 hover:text-red-500">
                    <Trash2 size={16} />
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