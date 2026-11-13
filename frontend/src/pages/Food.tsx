import { useEffect, useState } from 'react';
import { Search, MapPin, Utensils, Star, Clock, Loader2, AlertCircle } from 'lucide-react';
import { swiggyApi, type SwiggyAddress, type SwiggyRestaurant } from '../api';

export function Food() {
  const [addresses, setAddresses] = useState<SwiggyAddress[]>([]);
  const [addressId, setAddressId] = useState('');
  const [query, setQuery] = useState('');
  const [restaurants, setRestaurants] = useState<SwiggyRestaurant[]>([]);
  const [mock, setMock] = useState(true);
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState('');
  const [searched, setSearched] = useState(false);

  useEffect(() => {
    swiggyApi.addresses()
      .then((result) => {
        setAddresses(result.addresses || []);
        setMock(result.is_mock);
        if (result.addresses?.length) setAddressId(result.addresses[0].id);
      })
      .catch((err) => setError(err?.response?.data?.detail || 'Could not load addresses.'))
      .finally(() => setInitialLoading(false));
  }, []);

  const search = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || !addressId || loading) return;
    setLoading(true);
    setError('');
    setNotice('');
    setSearched(true);
    try {
      const result = await swiggyApi.search(query.trim(), addressId);
      setRestaurants(result.restaurants || []);
      setMock(result.is_mock);
      setNotice(result.notice || '');
    } catch (err: any) {
      setRestaurants([]);
      setError(err?.response?.data?.detail || 'Restaurant search failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-[#0b0910] px-4 py-8 text-white md:px-8">
      <div className="mx-auto max-w-6xl">
        <section className="relative overflow-hidden rounded-3xl border border-purple-300/15 bg-gradient-to-br from-[#28182f] via-[#17111f] to-[#100e16] p-7 md:p-12">
          <div className="text-xs font-bold tracking-[.2em] text-purple-300">WARIK FOOD DISCOVERY</div>
          <div className="mt-6 flex items-center justify-between gap-5">
            <div>
              <h1 className="text-4xl font-extrabold leading-tight tracking-tight md:text-6xl">
                Something good<br/><span className="text-purple-300">is on the menu.</span>
              </h1>
              <p className="mt-4 max-w-xl text-sm leading-7 text-white/60">
                Tell Warik what you are craving. Explore restaurants around your delivery address.
              </p>
            </div>
            <Utensils className="hidden h-20 w-20 text-purple-200/40 md:block" strokeWidth={1}/>
          </div>
        </section>

        <section className="mt-6 rounded-2xl border border-white/10 bg-[#15121b] p-5 md:p-7">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-[10px] font-bold tracking-[.2em] text-purple-300">DISCOVER SOMETHING DELICIOUS</div>
              <h2 className="mt-2 text-xl font-bold">What are you craving?</h2>
            </div>
            <span className={`rounded-full border px-3 py-1.5 text-xs ${mock ? 'border-amber-300/20 bg-amber-300/10 text-amber-200' : 'border-green-300/20 bg-green-300/10 text-green-200'}`}>
              {mock ? '● Demo data' : '● Live provider'}
            </span>
          </div>

          <form onSubmit={search} className="mt-6 grid gap-3 md:grid-cols-[1fr_1fr_auto]">
            <label className="text-xs text-white/60">
              Search dishes or cuisines
              <div className="mt-2 flex h-12 items-center gap-3 rounded-xl border border-white/10 bg-black/20 px-4 focus-within:border-purple-400">
                <Search size={17} className="text-purple-300"/>
                <input
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  placeholder="Biryani, pizza, South Indian..."
                  className="w-full bg-transparent text-sm text-white outline-none placeholder:text-white/30"
                  maxLength={100}
                />
              </div>
            </label>
            <label className="text-xs text-white/60">
              Delivery address
              <div className="mt-2 flex h-12 items-center gap-3 rounded-xl border border-white/10 bg-black/20 px-4">
                <MapPin size={17} className="shrink-0 text-purple-300"/>
                <select
                  value={addressId}
                  onChange={e => setAddressId(e.target.value)}
                  disabled={initialLoading || !addresses.length}
                  className="w-full min-w-0 bg-transparent text-sm text-white outline-none"
                >
                  {initialLoading && <option value="">Loading addresses...</option>}
                  {!initialLoading && !addresses.length && <option value="">No address available</option>}
                  {addresses.map(a => <option className="bg-[#17131c]" key={a.id} value={a.id}>
                    {a.addressCategory || 'Address'} — {a.addressLine || a.id}
                  </option>)}
                </select>
              </div>
            </label>
            <button
              disabled={loading || !query.trim() || !addressId}
              className="mt-auto flex h-12 items-center justify-center gap-2 rounded-xl bg-purple-700 px-6 text-sm font-bold transition hover:bg-purple-600 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {loading ? <Loader2 size={17} className="animate-spin"/> : <Search size={17}/>}
              {loading ? 'Searching...' : 'Find food'}
            </button>
          </form>
        </section>

        {error && <div role="alert" className="mt-5 flex items-center gap-3 rounded-xl border border-red-400/20 bg-red-400/10 p-4 text-sm text-red-200">
          <AlertCircle size={18}/>{error}
        </div>}
        {notice && <p className="mt-4 rounded-xl border border-amber-300/20 bg-amber-300/5 p-3 text-xs text-amber-200">{notice}</p>}

        <section className="mt-9">
          <div className="flex items-end justify-between">
            <div>
              <div className="text-[10px] font-bold tracking-[.2em] text-purple-300">YOUR DISCOVERY</div>
              <h2 className="mt-2 text-2xl font-bold">{searched ? `Results for “${query}”` : 'Ready when you are'}</h2>
            </div>
            {searched && <span className="text-xs text-white/40">{restaurants.length} places</span>}
          </div>

          {loading ? (
            <div className="mt-5 flex min-h-48 flex-col items-center justify-center gap-3 rounded-2xl border border-white/10 text-white/50">
              <Loader2 size={30} className="animate-spin text-purple-300"/>
              <span className="text-sm">Finding restaurants...</span>
            </div>
          ) : restaurants.length ? (
            <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {restaurants.map(r => (
                <article key={r.id} className="overflow-hidden rounded-2xl border border-white/10 bg-[#15121b] transition hover:-translate-y-1 hover:border-purple-300/30">
                  <div className="flex h-28 items-center justify-center bg-gradient-to-br from-[#34223e] to-[#17131e]">
                    <Utensils size={32} className="text-purple-200/60"/>
                    <span className="ml-4 rounded-full border border-green-300/20 bg-green-300/10 px-2 py-1 text-[9px] font-bold tracking-wider text-green-200">OPEN</span>
                  </div>
                  <div className="p-5">
                    <h3 className="font-bold">{r.name}</h3>
                    <p className="mt-1 text-xs text-white/45">{r.cuisines?.join(' · ') || 'Cuisine not specified'}</p>
                    <div className="mt-5 flex flex-wrap gap-4 text-xs text-white/65">
                      {r.avgRating != null && <span className="flex items-center gap-1"><Star size={13} className="text-amber-300"/>{r.avgRating}</span>}
                      {r.distanceKm != null && <span className="flex items-center gap-1"><MapPin size={13}/>{r.distanceKm} km</span>}
                      {r.deliveryTimeMinutes != null && <span className="flex items-center gap-1"><Clock size={13}/>{r.deliveryTimeMinutes} min</span>}
                    </div>
                    <div className="mt-4 border-t border-white/10 pt-3 text-[10px] text-purple-200/70">{mock ? 'Sample listing · Demo only' : 'Swiggy Food result'}</div>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="mt-5 flex min-h-48 flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 px-5 text-center">
              <Utensils size={28} className="text-purple-300/60"/>
              <strong className="mt-4 text-sm">{searched ? 'No matching open restaurants' : 'Your next favourite meal starts here'}</strong>
              <p className="mt-2 max-w-md text-xs leading-6 text-white/40">
                {searched ? 'Try another dish or cuisine.' : 'Search for a dish, cuisine or restaurant to see matching places.'}
              </p>
            </div>
          )}
        </section>

        <p className="mt-7 text-[10px] leading-5 text-white/35">
          {mock
            ? 'Demo environment: sample listings only. These are not live Swiggy restaurants, prices or delivery estimates.'
            : 'Provider results may change. Verify all details in Swiggy before placing an order.'}
        </p>
      </div>
    </main>
  );
}
