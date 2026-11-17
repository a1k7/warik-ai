import {
  Plane,
  Building2,
  Car,
  MapPin,
  ExternalLink,
  Check,
  RefreshCw,
  AlertTriangle,
  ArrowRight,
  Map,
  Clock,
  CalendarDays,
  Sparkles,
  Image as ImageIcon,
  ShieldCheck,
} from 'lucide-react';
import { useState } from 'react';

interface TripData {
  type: 'trip_summary';
  destination: string;
  flights: any[];
  hotels: any[];
  cabs: any;
  itinerary: any;
  failures: any[];
  flight_searches?: any[];
  flight_groups?: any[];
}

function HotelImage({ src, name }: { src?: string; name: string }) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return (
      <div className="h-48 w-full bg-gradient-to-br from-[#492633] via-[#30202B] to-[#171319] flex flex-col items-center justify-center gap-2">
        <ImageIcon size={28} className="text-[#C99AA4]/60" />
        <span className="text-[10px] uppercase tracking-[0.2em] text-[#C99AA4]/60">
          Image unavailable
        </span>
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={name}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className="h-48 w-full object-cover transition-transform duration-700 group-hover:scale-[1.04]"
    />
  );
}

function ActivityImage({ activity }: { activity: any }) {
  const [failed, setFailed] = useState(false);

  if (failed || !activity.image_url) {
    return (
      <div className="h-32 sm:h-40 bg-gradient-to-br from-[#492633] via-[#30202B] to-[#171319] flex items-center justify-center">
        <ImageIcon size={24} className="text-[#C99AA4]/60" />
      </div>
    );
  }

  return (
    <div>
      <img
        src={activity.image_url}
        alt={activity.name}
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
        className="h-40 sm:h-48 w-full object-cover"
      />
      {(activity.image_credit || activity.image_source_url) && (
        <div className="px-3 py-2 flex justify-between items-center gap-2 bg-black/20">
          <span className="text-[10px] text-[#BCA7AF] truncate">
            {activity.image_credit || "Image source"}
          </span>
          {activity.image_source_url && (
            <a
              href={activity.image_source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[10px] text-[#D6A8B3] shrink-0 hover:text-white"
            >
              Source ↗
            </a>
          )}
        </div>
      )}
    </div>
  );
}

function ActivityGroup({
  label,
  activities,
}: {
  label: string;
  activities: any[];
}) {
  if (!activities?.length) return null;

  return (
    <div className="flex gap-3">
      <div className="w-1 rounded-full bg-[#A96C7C]/50 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-[10px] uppercase tracking-[0.2em] text-[#C99AA4] font-semibold mb-2">
          {label}
        </p>
        <div className="grid gap-2">
          {activities.map((activity, index) => (
            <div
              key={`${label}-${index}`}
              className="rounded-xl bg-white/[0.035] border border-white/[0.055] overflow-hidden"
            >
              {activity.image_url ? (
                <ActivityImage activity={activity} />
              ) : (
                <div className="h-32 sm:h-40 bg-gradient-to-br from-[#492633] via-[#30202B] to-[#171319] flex items-center justify-center">
                  <div className="text-center">
                    <ImageIcon size={24} className="text-[#C99AA4]/60 mx-auto mb-2" />
                    <span className="text-[9px] uppercase tracking-[0.2em] text-[#C99AA4]/60">
                      Photo unavailable
                    </span>
                  </div>
                </div>
              )}
              <div className="p-3">
              <div className="flex items-start gap-2">
                <Clock size={13} className="text-[#C99AA4] mt-1 shrink-0" />
                <div className="min-w-0">
                  <p className="text-sm text-[#FAF7F3] font-medium">
                    {activity.name}
                  </p>
                  {activity.suggested_time && (
                    <p className="text-xs text-[#BCA7AF] mt-1">
                      {activity.suggested_time}
                    </p>
                  )}
                  {activity.description && (
                    <p className="text-xs text-[#BCA7AF]/80 mt-1 leading-relaxed">
                      {activity.description}
                    </p>
                  )}
                  {activity.map_url && (
                    <a
                      href={activity.map_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-[#D6A8B3] mt-2 hover:text-white"
                    >
                      Explore location <ExternalLink size={11} />
                    </a>
                  )}
                </div>
              </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export const TripResultCard = ({
  data,
  onSelectHotel,
  onSelectFlight,
  onRefreshFlight,
}: {
  data: TripData;
  onSelectHotel?: (hotel: any, context: any) => void;
  onSelectFlight?: (flight: any) => void;
  onRefreshFlight?: (offerId: string) => void;
}) => {
  if (!data) return null;

  const hotels = data.hotels || [];
  const days = data.itinerary?.days || [];
  const budget = data.itinerary?.budget;
  const flightSearches = data.flight_searches ?? [];
  const flightGroups = data.flight_groups?.length
    ? data.flight_groups
    : (data.flights?.length ? [{ items: data.flights }] : []);

  const displayTitle =
    !data.destination || data.destination === 'Your Trip'
      ? 'Your Travel Plan'
      : data.destination;

  return (
    <div className="w-full flex flex-col gap-5 mt-5 text-[#FAF7F3] animate-in fade-in slide-in-from-bottom-4 duration-500">

      {/* DESTINATION HERO */}
      <section className="relative overflow-hidden rounded-[24px] border border-[#B77B89]/30 bg-gradient-to-br from-[#702D3C] via-[#452331] to-[#171319] shadow-2xl">
        <div className="absolute -right-12 -top-16 w-64 h-64 rounded-full border border-white/[0.08]" />
        <div className="absolute -right-4 -top-8 w-44 h-44 rounded-full border border-white/[0.08]" />
        <div className="absolute right-8 bottom-[-90px] w-56 h-56 rounded-full bg-[#D3A1AD]/10 blur-3xl" />

        <div className="relative z-10 p-6 sm:p-8">
          <div className="flex justify-between items-start gap-4">
            <div>
              <div className="flex items-center gap-2 text-[#E6BAC4] text-[10px] font-bold tracking-[0.25em] uppercase mb-4">
                <Sparkles size={13} />
                Curated by Warik
              </div>

              <h2 className="text-3xl sm:text-4xl font-semibold tracking-tight">
                {displayTitle}
              </h2>

              <p className="text-[#E8C9D0]/80 text-sm mt-2">
                Your journey, thoughtfully put together.
              </p>
            </div>

            <span className="shrink-0 rounded-full border border-white/20 bg-black/15 px-3 py-2 text-[10px] uppercase tracking-wider text-[#F6DDE3]">
              {data.failures?.length ? 'Partially ready' : 'Plan ready'}
            </span>
          </div>

          <div className="flex flex-wrap gap-4 mt-7 pt-5 border-t border-white/15">
            {data.itinerary?.travellers && (
              <div className="text-xs text-[#F3DCE1]">
                <span className="block text-[9px] uppercase tracking-widest text-[#D6A8B3] mb-1">
                  Travellers
                </span>
                {data.itinerary.travellers} people
              </div>
            )}
            {days.length > 0 && (
              <div className="text-xs text-[#F3DCE1]">
                <span className="block text-[9px] uppercase tracking-widest text-[#D6A8B3] mb-1">
                  Duration
                </span>
                {days.length} days
              </div>
            )}
            {hotels.length > 0 && (
              <div className="text-xs text-[#F3DCE1]">
                <span className="block text-[9px] uppercase tracking-widest text-[#D6A8B3] mb-1">
                  Stays found
                </span>
                {hotels.length} options
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ITINERARY */}
      {days.length > 0 && (
        <section className="rounded-[22px] border border-[#702D3C]/40 bg-[#30252A] p-5 sm:p-6 shadow-lg">
          <div className="flex items-center justify-between gap-3 mb-5">
            <div>
              <div className="flex items-center gap-2 text-[#D6A8B3] text-[10px] uppercase tracking-[0.2em] font-bold">
                <Map size={14} /> Your journey
              </div>
              <h3 className="text-xl font-semibold mt-1">Day by day</h3>
            </div>
            <CalendarDays className="text-[#C99AA4]" size={22} />
          </div>

          <div className="flex flex-col gap-4">
            {days.map((day: any) => (
              <article
                key={day.day}
                className="rounded-2xl border border-white/[0.07] bg-[#1A1417] overflow-hidden"
              >
                <div className="p-4 sm:p-5">
                  <div className="flex items-start justify-between gap-3 mb-4">
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.2em] text-[#C99AA4] font-bold">
                        Day {day.day}
                      </p>
                      <h4 className="text-base font-semibold mt-1">
                        {day.title?.replace(/^Day\s*\d+\s*[—-]?\s*/i, '') || `Day ${day.day}`}
                      </h4>
                    </div>
                    {day.date && (
                      <span className="text-xs text-[#BCA7AF] shrink-0">
                        {day.date}
                      </span>
                    )}
                  </div>

                  <div className="grid gap-4">
                    <ActivityGroup label="Morning" activities={day.morning} />
                    <ActivityGroup label="Afternoon" activities={day.afternoon} />
                    <ActivityGroup label="Evening" activities={day.evening} />
                  </div>

                  {day.meal_suggestions?.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-white/[0.07]">
                      <p className="text-[10px] uppercase tracking-[0.2em] text-[#C99AA4] font-semibold mb-2">
                        Food suggestions
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {day.meal_suggestions.map((meal: any, i: number) => (
                          <span
                            key={i}
                            className="rounded-full border border-[#A96C7C]/30 bg-[#702D3C]/20 px-3 py-1.5 text-xs text-[#F1DDE2]"
                          >
                            {meal.name}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {/* EVIDENCE-AWARE BUDGET */}
      {budget && (
        <section className="rounded-[22px] border border-[#702D3C]/40 bg-[#30252A] p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-[#D6A8B3] text-[10px] uppercase tracking-[0.2em] font-bold">
                <ShieldCheck size={14} /> Budget reality check
              </div>
              <h3 className="text-xl font-semibold mt-1">What this trip may cost</h3>
              <p className="text-xs text-[#BCA7AF] mt-1">
                Estimates and provider prices are kept separate.
              </p>
            </div>
            <span className="rounded-full border border-amber-400/25 bg-amber-400/10 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wide text-amber-200">
              {budget.is_partial ? 'Partial estimate' : 'Planning estimate'}
            </span>
          </div>

          <div className="mt-4 grid gap-2">
            {(budget.items || []).map((item: any, index: number) => (
              <div key={`${item.category}-${index}`} className="flex items-center justify-between gap-3 rounded-xl bg-[#1A1417] border border-white/[0.06] px-3 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-[#FAF7F3]">{item.category}</p>
                  {item.note && <p className="text-[10px] text-[#BCA7AF] mt-1">{item.note}</p>}
                  <p className="text-[9px] uppercase tracking-wider mt-1 text-[#C99AA4]">
                    {item.classification === 'ESTIMATE'
                      ? 'Modelled estimate'
                      : item.classification === 'UNAVAILABLE'
                        ? 'Not verified / excluded'
                        : item.classification || 'Unclassified'}
                  </p>
                </div>
                <p className="shrink-0 text-sm font-semibold text-[#F1DDE2] tabular-nums">
                  {typeof item.amount === 'number'
                    ? new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(item.amount)
                    : 'Not included'}
                </p>
              </div>
            ))}
          </div>

          <div className="mt-4 rounded-xl border border-white/10 bg-black/10 p-4">
            <div className="flex items-end justify-between gap-3">
              <div>
                <p className="text-[10px] uppercase tracking-wider text-[#BCA7AF]">Estimated total</p>
                <p className="text-2xl font-semibold text-white mt-1 tabular-nums">
                  {typeof budget.total_estimate === 'number'
                    ? new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(budget.total_estimate)
                    : 'Unavailable'}
                </p>
              </div>
              {typeof budget.remaining === 'number' && (
                <div className="text-right">
                  <p className="text-[10px] uppercase tracking-wider text-[#BCA7AF]">Remaining vs budget</p>
                  <p className={`text-lg font-semibold mt-1 tabular-nums ${budget.remaining >= 0 ? 'text-emerald-300' : 'text-amber-300'}`}>
                    {new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(budget.remaining)}
                  </p>
                </div>
              )}
            </div>
            {Array.isArray(budget.excludes) && budget.excludes.length > 0 && (
              <p className="text-[10px] text-amber-200/90 mt-3">
                Excluded from total: {budget.excludes.join(', ')}.
              </p>
            )}
          </div>
          <p className="text-[10px] leading-relaxed text-[#BCA7AF] mt-3">
            Estimates use planning assumptions, not live price quotes. Confirm transport fares, accommodation totals and attraction fees with providers before relying on this budget.
          </p>
        </section>
      )}

      {/* HOTELS */}
      {hotels.length > 0 && (
        <section className="rounded-[22px] border border-[#702D3C]/40 bg-[#30252A] p-5 sm:p-6 shadow-lg">
          <div className="mb-5">
            <div className="flex items-center gap-2 text-[#D6A8B3] text-[10px] uppercase tracking-[0.2em] font-bold">
              <Building2 size={14} /> Hotel options
            </div>
            <h3 className="text-xl font-semibold mt-1">Places to stay</h3>
            <p className="text-xs text-[#BCA7AF] mt-1">
              Compare available properties and booking options.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {hotels.map((hotel: any, index: number) => (
              <article
                key={`${hotel.name}-${index}`}
                className="group overflow-hidden rounded-2xl border border-white/[0.08] bg-[#1A1417] hover:border-[#C99AA4]/40 transition-all duration-300"
              >
                <div className="overflow-hidden">
                  <HotelImage src={hotel.image_url} name={hotel.name} />
                </div>

                <div className="p-4">
                  <div className="flex justify-between items-start gap-3">
                    <div className="min-w-0">
                      <h4 className="font-semibold text-[#FAF7F3] leading-snug">
                        {hotel.name}
                      </h4>
                      {(hotel.city || hotel.address) && (
                        <p className="flex items-start gap-1.5 text-xs text-[#BCA7AF] mt-2">
                          <MapPin size={12} className="mt-0.5 shrink-0" />
                          {hotel.city || hotel.address}
                        </p>
                      )}
                    </div>

                    {hotel.rating && hotel.rating !== 'Not provided' && (
                      <span className="shrink-0 rounded-lg bg-[#B88A4A]/15 border border-[#B88A4A]/20 px-2 py-1 text-xs text-[#E6C58D]">
                        ★ {hotel.rating}
                      </span>
                    )}
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-3 border-t border-white/[0.07] pt-3">
                    <div>
                      <p className="text-[9px] uppercase tracking-wider text-[#A98D98]">
                        Total stay
                      </p>
                      <p className="text-base font-semibold mt-1">
                        {hotel.price || hotel.total_stay || 'Price unavailable'}
                      </p>
                    </div>
                    <div>
                      <p className="text-[9px] uppercase tracking-wider text-[#A98D98]">
                        Per night
                      </p>
                      <p className="text-sm font-medium mt-1">
                        {hotel.price_per_night || 'Not available'}
                      </p>
                    </div>
                  </div>

                  {(hotel.check_in || hotel.check_out) && (
                    <p className="text-[11px] text-[#BCA7AF] mt-3">
                      {hotel.check_in || 'Check-in unavailable'} → {hotel.check_out || 'Check-out unavailable'}
                    </p>
                  )}

                  {hotel.booking_url && (
                    <a
                      href={hotel.booking_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-4 flex items-center justify-center gap-2 w-full rounded-xl bg-[#702D3C] hover:bg-[#873D50] py-3 text-xs font-semibold text-white transition-colors"
                    >
                      View booking options <ExternalLink size={13} />
                    </a>
                  )}
                  {onSelectHotel && (
                    <button
                      type="button"
                      onClick={() => onSelectHotel(hotel, {
                        city: hotel.city || data.destination,
                        check_in: hotel.check_in,
                        check_out: hotel.check_out,
                      })}
                      className="mt-2 flex items-center justify-center gap-2 w-full rounded-xl border border-[#C99AA4]/30 bg-white/[0.04] hover:bg-white/[0.08] py-3 text-xs font-semibold text-[#E7C2CA] transition-colors"
                    >
                      Use this stay in my trip <Check size={13} />
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>
        </section>
      )}


      {/* Provider fallback: retain the route handoff when structured live offers are unavailable. */}
      {(!data.flights || data.flights.length === 0) && flightSearches.length > 0 && (
        <section className="rounded-[22px] border border-[#702D3C]/40 bg-[#30252A] p-5 sm:p-6">
          <div className="flex items-center gap-2 text-[#D6A8B3] text-[10px] uppercase tracking-[0.2em] font-bold mb-2">
            <Plane size={14} /> Flight search
          </div>
          <h3 className="text-lg font-semibold">Check current flight options</h3>
          <p className="text-xs text-[#BCA7AF] mt-2">
            {flightSearches[0].live_inventory === false
              ? "Live flight offers were not available from the connected provider in this session. This link opens an external route search; it is not a verified fare quote."
              : "The connected provider returned no matching flight offers. You can also check the route directly."}
          </p>
          {flightSearches[0].search_url && (
            <a
              href={flightSearches[0].search_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-4 inline-flex items-center gap-2 rounded-xl bg-[#702D3C] hover:bg-[#873D50] px-4 py-3 text-xs font-semibold text-white"
            >
              Open external flight search <ExternalLink size={13} />
            </a>
          )}
        </section>
      )}

      {/* FLIGHTS */}
      {flightGroups.length > 0 && (
        <section className="rounded-[22px] border border-[#702D3C]/40 bg-[#30252A] p-5 sm:p-6 shadow-lg">
          <div className="flex items-center gap-2 text-[#D6A8B3] text-[10px] uppercase tracking-[0.2em] font-bold mb-1">
            <Plane size={14} /> Flight options
          </div>
          <h3 className="text-xl font-semibold mb-4">
            {flightGroups.length > 1 ? 'Your flight legs' : 'Getting there'}
          </h3>

          <div className="grid gap-4">
            {flightGroups.map((group: any, groupIndex: number) => {
              const groupItems = Array.isArray(group.items) ? group.items : [];
              const legLabel = flightGroups.length === 2
                ? (groupIndex === 0 ? 'Outbound' : 'Return')
                : (flightGroups.length > 1 ? `Leg ${groupIndex + 1}` : 'Flight options');
              return (
                <div key={group.step_id || groupIndex} className="rounded-2xl border border-white/[0.07] bg-[#21191D] p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.18em] font-bold text-[#C99AA4]">{legLabel}</p>
                      {(group.origin || group.destination) && (
                        <p className="text-sm font-semibold mt-1">
                          {group.origin || '—'} <ArrowRight size={13} className="inline mx-1 text-[#C99AA4]"/> {group.destination || '—'}
                        </p>
                      )}
                      {group.date && (
                        <p className="text-[11px] text-[#BCA7AF] mt-1">{group.date}</p>
                      )}
                      {Number(group.filters_applied?.passengers) > 0 && (
                        <p className="text-[10px] text-[#BCA7AF]/80 mt-1">
                          Prices for {Number(group.filters_applied.passengers)} adult{Number(group.filters_applied.passengers) === 1 ? '' : 's'}
                        </p>
                      )}
                    </div>
                    {group.source && <span className="text-[10px] text-[#BCA7AF]">{group.source}</span>}
                  </div>

                  {groupItems.length > 0 ? (
                    <div className="grid gap-3">
                      {groupItems.map((flight: any, index: number) => (
                        <article key={flight.offer_id || index} className="rounded-xl bg-[#1A1417] border border-white/[0.07] p-4">
                          <div className="flex items-center justify-between gap-3 mb-3">
                            <p className="text-lg font-semibold">{flight.price || 'Price unavailable'}</p>
                            <span className="text-xs text-[#D6A8B3]">
                              {flight.stops === 0 ? 'Non-stop' : `${flight.stops ?? '—'} stop(s)`}
                            </span>
                          </div>

                          {flight.segments?.map((segment: any, j: number) => (
                            <div key={j} className="border-t border-white/[0.07] pt-3 mt-2">
                              <div className="flex justify-between text-sm gap-2">
                                <span className="font-medium">{segment.airline} {segment.flight_number}</span>
                                <span className="text-[#C99AA4] text-xs">{segment.departure}</span>
                              </div>
                              <div className="flex items-center gap-2 text-xs text-[#BCA7AF] mt-2">
                                <span>{segment.origin}</span>
                                <ArrowRight size={12} />
                                <span>{segment.destination}</span>
                                <span className="ml-auto">{segment.arrival}</span>
                              </div>
                            </div>
                          ))}

                          <div className="flex flex-wrap gap-2 mt-4">
                            {flight.offer_id && onSelectFlight && (
                              <button
                                type="button"
                                onClick={() => onSelectFlight(flight)}
                                className="inline-flex items-center gap-2 rounded-xl bg-[#702D3C] hover:bg-[#873D50] px-3 py-2.5 text-xs font-semibold text-white"
                              >
                                Continue with this flight <Check size={12} />
                              </button>
                            )}
                            {flight.offer_id && onRefreshFlight && (
                              <button
                                type="button"
                                onClick={() => onRefreshFlight(flight.offer_id)}
                                className="inline-flex items-center gap-2 rounded-xl border border-[#C99AA4]/30 bg-white/[0.04] px-3 py-2.5 text-xs font-semibold text-[#E7C2CA]"
                              >
                                Refresh live price <RefreshCw size={12} />
                              </button>
                            )}
                            {!flight.offer_id && flight.url && (
                              <a href={flight.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 rounded-xl bg-[#702D3C] hover:bg-[#873D50] px-3 py-2.5 text-xs font-semibold text-white">
                                View flight <ExternalLink size={12} />
                              </a>
                            )}
                          </div>
                          {flight.expires_at && (
                            <p className="text-[10px] text-[#BCA7AF] mt-2">Offer expiry: {new Date(flight.expires_at).toLocaleString('en-IN')}</p>
                          )}
                        </article>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-[#BCA7AF]">
                      No structured live offers were returned for this leg.
                      {group.search_url && (
                        <a className="ml-1 text-[#D6A8B3] underline" href={group.search_url} target="_blank" rel="noopener noreferrer">Open route search</a>
                      )}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* TRANSPORT */}
      {data.cabs && Object.keys(data.cabs).length > 0 && (
        <section className="rounded-[22px] border border-[#702D3C]/40 bg-[#30252A] p-5 sm:p-6">
          <div className="flex items-center gap-2 text-[#D6A8B3] text-[10px] uppercase tracking-[0.2em] font-bold">
            <Car size={14} /> Ground transport
          </div>
          <h3 className="text-xl font-semibold mt-1 mb-4">Continue your journey</h3>

          <p className="text-xs text-[#BCA7AF] mb-3">
            These links open the provider app. Check its live fare and pickup details there; Warik has not booked a ride.
          </p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(data.cabs).map(([key, url]: [string, any]) => (
              <a
                key={key}
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 rounded-xl border border-white/10 bg-[#1A1417] px-4 py-3 text-sm capitalize hover:border-[#C99AA4]/50 transition-colors"
              >
                Continue with {key} <ExternalLink size={13} />
              </a>
            ))}
          </div>
        </section>
      )}

      {/* FAILURES */}
      {data.failures?.length > 0 && (
        <section className="rounded-2xl border border-amber-500/20 bg-amber-950/20 p-4">
          <p className="flex items-center gap-2 text-sm font-semibold text-amber-300">
            <AlertTriangle size={16} />
            Some services need attention
          </p>
          {data.failures.map((failure: any, index: number) => (
            <p key={index} className="text-xs text-amber-100/70 mt-2">
              {failure.tool}: {failure.error}
            </p>
          ))}
        </section>
      )}
    </div>
  );
};