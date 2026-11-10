import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import { Hotel, Utensils, Map, Trash2, ExternalLink, Calendar } from 'lucide-react';

export const Saved = () => {
  const [activeTab, setActiveTab] = useState<'hotels' | 'restaurants' | 'trips'>('hotels');
  const [hotels, setHotels] = useState<any[]>([]);
  const [restaurants, setRestaurants] = useState<any[]>([]);
  const [trips, setTrips] = useState<any[]>([]);
  const navigate = useNavigate();

  const loadData = async () => {
    try {
      if (activeTab === 'hotels') {
        const res = await api.get('/saved/hotels');
        setHotels(res.data);
      } else if (activeTab === 'restaurants') {
        const res = await api.get('/saved/restaurants');
        setRestaurants(res.data);
      } else {
        const res = await api.get('/saved/trips');
        setTrips(res.data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => { loadData(); }, [activeTab]);

  const deleteHotel = async (id: number) => {
    await api.delete(`/saved/hotels/${id}`);
    loadData();
  };

  const deleteTrip = async (id: number) => {
    await api.delete(`/saved/trips/${id}`);
    loadData();
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold text-white">My Saved</h1>
        <div className="flex gap-2 bg-jcard p-1 rounded-lg border border-jmuted/20">
          <button onClick={() => setActiveTab('hotels')} className={`px-4 py-2 text-sm rounded-md transition ${activeTab === 'hotels' ? 'bg-jprimary text-white' : 'text-jmuted hover:text-white'}`}>Hotels</button>
          <button onClick={() => setActiveTab('restaurants')} className={`px-4 py-2 text-sm rounded-md transition ${activeTab === 'restaurants' ? 'bg-jprimary text-white' : 'text-jmuted hover:text-white'}`}>Restaurants</button>
          <button onClick={() => setActiveTab('trips')} className={`px-4 py-2 text-sm rounded-md transition ${activeTab === 'trips' ? 'bg-jprimary text-white' : 'text-jmuted hover:text-white'}`}>Trips</button>
        </div>
      </div>

      {activeTab === 'hotels' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {hotels.length === 0 ? <p className="text-jmuted">No saved hotels yet.</p> : hotels.map(h => (
            <div key={h.id} className="bg-jcard border border-jprimary/30 rounded-xl p-4 flex flex-col gap-2">
              <div className="flex justify-between items-start">
                <h3 className="font-bold text-white">{h.name}</h3>
                <button onClick={() => deleteHotel(h.id)} className="text-red-400 hover:text-red-300"><Trash2 size={16}/></button>
              </div>
              <p className="text-xs text-jmuted">{h.address}</p>
              {h.check_in && <p className="text-xs text-jsecondary">{h.check_in} to {h.check_out}</p>}
              <div className="flex justify-between items-center mt-2">
                <span className="text-sm font-bold">{h.price || 'N/A'}</span>
                <a href={h.booking_url} target="_blank" className="text-xs bg-jprimary px-3 py-1.5 rounded text-white flex items-center gap-1">Book <ExternalLink size={12}/></a>
              </div>
            </div>
          ))}
        </div>
      )}

      {activeTab === 'restaurants' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {restaurants.length === 0 ? <p className="text-jmuted">No saved restaurants yet.</p> : restaurants.map(r => (
            <div key={r.id} className="bg-jcard border border-jprimary/30 rounded-xl p-4 flex flex-col gap-2">
              <h3 className="font-bold text-white">{r.name}</h3>
              <p className="text-xs text-jmuted">{r.location}</p>
            </div>
          ))}
        </div>
      )}

      {activeTab === 'trips' && (
        <div className="grid grid-cols-1 gap-4">
          {trips.length === 0 ? <p className="text-jmuted">No saved trips yet.</p> : trips.map(t => (
            <div key={t.id} className="bg-jcard border border-jprimary/30 rounded-xl p-4 flex flex-col gap-2">
              <div className="flex justify-between items-start">
                <h3 className="font-bold text-white">{t.destination} - {t.days} Days</h3>
                <button onClick={() => deleteTrip(t.id)} className="text-red-400 hover:text-red-300"><Trash2 size={16}/></button>
              </div>
              <p className="text-xs text-jmuted">Created {new Date(t.created_at).toLocaleDateString()}</p>
              <div className="mt-2 text-sm text-jsecondary bg-jbg p-2 rounded">
                {t.itinerary_data?.days?.map((d: any) => (
                  <div key={d.day}>Day {d.day}: {d.activities[0]?.name}</div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
