import React, { useState } from 'react';
import { foodService } from '../services/api';
import { Search, ExternalLink, Utensils } from 'lucide-react';

export const Food: React.FC = () => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<{ disclaimer: string; external_links: Record<string, string> } | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    try {
      const res = await foodService.search(query);
      setResults(res);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-charcoal">Food Discovery</h1>
      
      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="E.g., vegetarian food in Bhopal under ₹500"
          className="flex-1 bg-white border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-burgundy/50"
        />
        <button type="submit" className="bg-burgundy text-white px-6 rounded-xl font-medium hover:bg-wine flex items-center gap-2">
          <Search size={18} /> Search
        </button>
      </form>

      {results && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 space-y-4">
          <div className="flex items-start gap-3 text-sm text-gray-600 bg-ivory p-4 rounded-xl">
            <Utensils size={20} className="text-burgundy flex-shrink-0" />
            <p>{results.disclaimer}</p>
          </div>
          <div className="flex gap-4">
            {Object.entries(results.external_links).map(([name, url]) => (
              <a key={name} href={url} target="_blank" rel="noreferrer" className="flex items-center gap-2 bg-burgundy text-white px-4 py-2 rounded-lg text-sm hover:bg-wine">
                Search on {name} <ExternalLink size={14} />
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};