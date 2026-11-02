import React, { useEffect, useState } from 'react';
import { travelService } from '../services/api';
import type { TravelPlan } from '../types';
import { MapPin } from 'lucide-react';

export const Travel: React.FC = () => {
  const [plans, setPlans] = useState<TravelPlan[]>([]);

  useEffect(() => {
    travelService.list().then(setPlans);
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-charcoal">Travel Plans</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {plans.length === 0 ? <p className="text-gray-500">No travel plans yet. Ask Warik to plan a trip!</p> : (
          plans.map(plan => (
            <div key={plan.id} className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
              <div className="flex items-center gap-2 mb-2 text-burgundy">
                <MapPin size={18} />
                <h3 className="font-bold">{plan.title}</h3>
              </div>
              <p className="text-sm text-gray-500 mb-4">{plan.origin} → {plan.destination}</p>
              {plan.budget && <p className="text-sm font-medium bg-ivory inline-block px-2 py-1 rounded">Budget: ₹{plan.budget}</p>}
            </div>
          ))
        )}
      </div>
    </div>
  );
};